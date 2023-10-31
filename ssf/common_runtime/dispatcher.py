# Copyright (c) 2022 Graphcore Ltd. All rights reserved.
import logging
import multiprocessing as mp
import os
import threading
import time
import sys
from collections import deque
from dataclasses import dataclass, field
from queue import Empty as QueueEmpty
from statistics import mean
from threading import Thread
from typing import Dict, List

from ssf.common_runtime.common import *
from ssf.common_runtime.config import Settings
from ssf.application import get_application

from ssf.results import *
from ssf.utils import temporary_cwd
from ssf.config import SSFConfig
from ssf.logger import configure_log_queue
from ssf.logger import get_log_queue


@dataclass
class Dispatcher:
    """Class to hold a single application queue from which to dispatch requests"""

    ctx = mp.get_context("spawn")

    settings: Settings
    application_id: str
    ssf_config: SSFConfig

    max_restart_reached: bool = False
    max_restart_threshold: int = 3
    missing = {}

    def __post_init__(self):
        # initialize multiprocessing resources
        ctx = self.ctx
        # Each process is a replica of the same application
        self.processes: List = [None] * self.settings.replicate_application
        self.input_queue: mp.Queue = ctx.Queue()
        self.output_queue: mp.Queue = ctx.Queue()

        self.max_restart_threshold = self.settings.max_allowed_restarts

        # Global switch to terminate all replica processes
        self.terminate: mp.Event = ctx.Event()

        # Each process is set "ready" after application startup() finishes
        self.ready = [ctx.Event() for _ in range(self.settings.replicate_application)]

        # A process failure count is incremented after each consecutive failure of application process.
        # It is reset to 0 as soon as the application process is running successfully.
        self.process_failure_counts = ctx.Manager().list(
            [0] * self.settings.replicate_application
        )

        self.log_queue: mp.Queue = get_log_queue()

    def start(self):
        logger = logging.getLogger("ssf")
        logger.debug("Start dispatcher enter")

        if self.log_queue is None:
            raise SSFExceptionInternalError("Error loading the logger")

        # Start processes that are not yet running.
        # We must avoid any live processes in 'self' to avoid a pickling issue when starting new processes.
        # This is why the current_processes are cached in a temporary local variable and merged
        # back with new_processes at the end.
        for idx, p in enumerate(self.processes):
            if p is not None:
                logger.debug(f"Initial {idx}:{p.pid} {p.is_alive()}")
        num_procs = len(self.processes)
        current_processes = self.processes
        new_processes = [None] * num_procs
        self.processes = [None] * num_procs
        for idx in range(len(self.processes)):
            if (
                not self.max_restart_reached
                and self.process_failure_counts[idx] >= self.max_restart_threshold
            ):
                # One time error when this Dispatcher first triggers `max_restart_reached` (=> not alive)
                self.max_restart_reached = True
                logger.error(
                    f"Dispatcher: Replica {idx} of {self.application_id} health check kept failing after {self.process_failure_counts[idx]} restarts."
                )
            if current_processes[idx] is not None:
                # Don't restart processes that are still/already running
                logger.info(
                    f"Dispatcher: Replica {idx} of {self.application_id} is already running."
                )
            elif self.max_restart_reached:
                # Don't keep attempting to restart once `max_restart_reached` for this Dispatcher.
                logger.warning(
                    f"Dispatcher: Replica {idx} of {self.application_id} is stopped, max restarts reached."
                )
            else:
                # Attempt to (re)start this process instance.
                self.ready[idx].clear()
                new_processes[idx] = self.ctx.Process(
                    target=self.process_loop,
                    args=(
                        os.getpid(),
                        self.input_queue,
                        self.output_queue,
                        self.ready[idx],
                        self.terminate,
                        self.log_queue,
                        idx,
                    ),
                )
                logger.info(
                    f"Starting {self.application_id} replica idx {idx} (process failure count {self.process_failure_counts[idx]})"
                )
                new_processes[idx].start()

        # Merge new processes with current processes.
        for idx in range(num_procs):
            self.processes[idx] = new_processes[idx] or current_processes[idx]

        for idx, p in enumerate(new_processes):
            if p is not None:
                logger.debug(f"New {idx}:{p.pid} {p.is_alive()}")

        for idx, p in enumerate(self.processes):
            if p is not None:
                logger.debug(f"Final {idx}:{p.pid} {p.is_alive()}")

        logger.debug("Start dispatcher exit")

    def stop(self):
        logger = logging.getLogger("ssf")
        logger.debug("Stop dispatcher enter")
        [ready.clear() for ready in self.ready]
        self.terminate.set()
        [p.join() for p in self.processes if p is not None]
        [p.close() for p in self.processes if p is not None]
        self.processes = [None] * len(self.processes)
        logger.debug(f"Stop dispatcher exit")

    def clean(self):
        # return True if all processes are alive
        # remove them otherwise
        logger = logging.getLogger("ssf")
        status = False
        for idx, p in enumerate(self.processes):
            if p and not p.is_alive():
                logger.error(
                    f"{self.application_id}:{idx} ({p.pid}) is not alive (exitcode {p.exitcode})."
                )
                self.processes[idx].close()
                self.processes[idx] = None
                status = True
        return status

    def process_loop(
        self,
        parent_pid,
        input_queue: mp.Queue,
        output_queue: mp.Queue,
        ready: mp.Event,
        terminate: mp.Event,
        log_queue: mp.Queue,
        index: int,
    ):
        exit_code = 0
        thread_ids = []

        try:
            # redirect process root logger to the queue
            configure_log_queue(log_queue)

            logger = logging.getLogger("ssf_dispatcher")
            logger.info(
                f"> [{index}] Dispatcher started for {self.application_id} [{parent_pid}->{os.getpid()}]"
            )

            # Get instance to serve the endpoint.
            logger.info(f"> [{index}] Getting user application instance")
            instance = get_application(self.ssf_config)
            app_file_dir = self.ssf_config.application.file_dir

            logger.info(f"instance={instance}")
            logger.info(f"> [{index}] Running app from {app_file_dir}")

            with temporary_cwd(app_file_dir):
                # Start it up.
                logger.info(f"> [{index}] Startup user application instance")
                startup_ret_val = instance.startup()
                if startup_ret_val != RESULT_OK:
                    raise SSFExceptionApplicationError(
                        startup_ret_val, f"[{index}] Application `startup` call failed."
                    )

                healthy = True
                ready.set()

                last_ready_watchdog = None

                def reset_watchdog_ready_period():
                    nonlocal last_ready_watchdog
                    if self.settings.watchdog_ready_period > 0:
                        last_ready_watchdog = time.time()

                reset_watchdog_ready_period()

                batching_start, batched_params, batched_meta = (None, [], [])
                max_batch_size = self.ssf_config.application.max_batch_size
                # Service the request (queue).
                logger.debug(f"[{index}] Dispatcher queue processing begin")
                logger.debug(
                    f"[{index}] Dispatcher settings batching_timeout={self.settings.batching_timeout} max_batch_size={max_batch_size}"
                )
                call_duration = deque(maxlen=self.settings.watchdog_request_average)

                while not terminate.is_set() and healthy:
                    try:
                        while (
                            not terminate.is_set()
                            and len(batched_params) != max_batch_size
                        ):
                            now = time.time()

                            if (
                                batching_start
                                and now - batching_start
                                > self.settings.batching_timeout
                            ):
                                break

                            if (
                                last_ready_watchdog is not None
                                and (now - last_ready_watchdog)
                                > self.settings.watchdog_ready_period
                            ):
                                last_ready_watchdog = now
                                logger.info(
                                    f"[{index}] Dispatcher polling application replica watchdog"
                                )
                                if instance.watchdog() != RESULT_OK:
                                    healthy = False
                                    raise SSFExceptionApplicationError(
                                        f"[{index}] Application `watchdog` call failed."
                                    )

                            # NOTE:
                            # This uses a timeout after 1 second so we can gracefully check for termination.
                            # We need to check that this doesn't add measurable latency for the scenario
                            # where we have intermittent requests.
                            thread_id, inputs = input_queue.get(timeout=1)
                            batching_start = (
                                time.time() if not batching_start else batching_start
                            )
                            params, meta = inputs[:2]
                            meta["replica"] = index

                            batched_params.append(params)
                            batched_meta.append(meta)
                            thread_ids.append(thread_id)

                        logger.debug(
                            f"[{index}] Dispatcher issuing request with params={batched_params} meta={batched_meta}"
                        )

                        chrono_start = time.time()
                        input = (
                            (batched_params, batched_meta)
                            if max_batch_size > 1
                            else (batched_params[0], batched_meta[0])
                        )
                        results = instance.request(*input)
                        chrono = time.time() - chrono_start

                        if max_batch_size > 1:
                            if not isinstance(results, list) or not all(
                                isinstance(r, dict) for r in results
                            ):
                                raise SSFExceptionApplicationError(
                                    f"[{index}] Expected result as list of dict for batched request (size {max_batch_size})"
                                )
                        else:
                            if not isinstance(results, dict):
                                raise SSFExceptionApplicationError(
                                    f"[{index}] Expected result as dict for unbatched request"
                                )

                        if not isinstance(results, list):
                            results = [results if results != None else {}]

                        # make sure every thread gets reply even if error
                        results += [{}] * (max_batch_size - len(results))

                        for r in [i for i in zip(thread_ids, results)]:
                            r[1][HEADER_METRICS_DISPATCH_LATENCY] = chrono
                            output_queue.put(r)

                        batching_start, batched_params, batched_meta, thread_ids = (
                            None,
                            [],
                            [],
                            [],
                        )

                        if self.settings.watchdog_request_threshold:
                            call_duration.append(chrono)
                        if (
                            len(call_duration) == self.settings.watchdog_request_average
                            and mean(call_duration)
                            > self.settings.watchdog_request_threshold
                        ):
                            logger.warning(
                                f"[{index}] Dispatcher duration watchdog triggered (avg {mean(call_duration)})."
                            )
                            break

                        # A successful request =>
                        # - reset the failure loop detection
                        # - reset period until next watchdog ready poll
                        self.process_failure_counts[index] = 0
                        reset_watchdog_ready_period()

                    except QueueEmpty:
                        pass
                    except KeyboardInterrupt:
                        pass

        except Exception as e:
            logger.exception(e)
            self.process_failure_counts[index] += 1
            logger.info(
                f"[{index}] Application instance failure counts: {self.process_failure_counts}"
            )
            for t_id in thread_ids:
                output_queue.put((t_id, None))
            if isinstance(e, SSFException):
                exit_code = e.result_code
            else:
                exit_code = RESULT_APPLICATION_ERROR

        try:
            if self.process_failure_counts:
                logger.info(f"[{index}] Failure count {self.process_failure_counts}")

            logger.debug(f"[{index}] Dispatcher queue processing end")
            ready.clear()

            # Shut it down.
            logger.info(f"> [{index}] Shutdown user application instance")

            instance.shutdown()
        except Exception as e:
            logger.exception(e)

        sys.exit(exit_code)

    def queue_request(self, data_dict: Dict):
        thread_id = threading.get_ident()
        self.input_queue.put([thread_id, data_dict])

    def get_result(self):
        result = None
        while True:
            if str(threading.get_ident()) in self.missing:
                result = self.missing[str(threading.get_ident())]
                del self.missing[str(threading.get_ident())]
                break
            else:
                pass
            try:
                result = self.output_queue.get(timeout=0.001)
                if result[0] != threading.get_ident():
                    # Handle synchronisation issues
                    # If the message was not for this thread
                    # Put the message in a dict so the other threads can find it in quicker time
                    self.missing[str(result[0])] = result
                else:
                    break
            except:
                pass
        return result[1]

    def queue_size(self):
        return self.input_queue.qsize()

    def is_alive(self):
        # liveness check is always up, unless
        # a replica process keep failing/restarting
        return not self.max_restart_reached

    def is_ready(self):
        # True if at least one replica is up and ready
        for idx, p in enumerate(self.processes):
            if p is not None and p.is_alive() and self.ready[idx].is_set():
                return True

    def all_ready(self):
        # True if all replicas are up and ready
        for idx, p in enumerate(self.processes):
            if p is None:
                return False
            if not p.is_alive():
                return False
            if not self.ready[idx].is_set():
                return False
        return True

    def all_alive(self):
        # True if all replica processes are alive
        return all(p.is_alive() for p in self.processes if p is not None)

    def exit_codes(self):
        # Returns list of exit codes for stopped processes
        return [
            p.exitcode for p in self.processes if p is not None and not p.is_alive()
        ]


@dataclass
class Applications:
    """Class to hold the running application(s)"""

    # Settings
    settings: Settings

    # List of applications declared as config files.
    ssf_config_list: List[str]
    notify_error_callback: callable
    result_code: int = RESULT_OK

    # Each application has a dispatcher (keyed on application id).
    dispatcher: Dict[str, Dispatcher] = field(default_factory=dict)
    watchdog_period: int = 10
    is_cancelled: bool = False
    started = False
    startup_failure = False
    stopped = True

    def is_ready(self):
        if self.started:
            return all([d.is_ready() for d in self.dispatcher.values()])
        else:
            return False

    def is_alive(self):
        if self.started:
            return (
                all([d.is_alive() for d in self.dispatcher.values()])
                and self.watchdog_thread.is_alive()
            )
        else:
            return not self.startup_failure

    def check_dispatcher_health(self):
        unhealthy = []
        for d in self.dispatcher.values():
            if d.clean():
                self.notify_error_callback(settings=self.settings)
                unhealthy.append(d)
        return unhealthy

    def watchdog(self):
        # Watchdog thread.
        # Restart dead workers
        logger = logging.getLogger("ssf")
        logger.debug("Watchdog enter")
        # self.watchdog_wake.acquire()
        while self.watchdog_period:
            unhealthy = self.check_dispatcher_health()
            for d in unhealthy:
                d.start()
            # self.watchdog_wake.wait(self.watchdog_period)
            time.sleep(self.watchdog_period)
        logger.debug("Watchdog exit")

    def start(self):
        # Initiate and start dispatcher(s).
        logger = logging.getLogger("ssf")
        logger.debug("Start enter")
        self.stopped = False

        # TODO:
        # Remove the multiple config code paths.
        # We only really support/expect a single config per application.
        for ssf_config in self.ssf_config_list:
            application_id = ssf_config.application.id
            self.dispatcher.update(
                {
                    application_id: Dispatcher(
                        self.settings,
                        application_id=application_id,
                        ssf_config=ssf_config,
                    )
                }
            )
            self.dispatcher[application_id].start()

        # self.watchdog_wake = threading.Condition()
        self.watchdog_thread = Thread(target=self.watchdog)
        self.watchdog_thread.start()

        # Wait for workers to be ready for this application.
        # If a replica process fails to start,
        # just quit with an error
        while True:
            time.sleep(1)
            if not all([d.all_alive() for d in self.dispatcher.values()]):
                logger.error(f"Dispatcher failed to start")

                # Get set of unique exit codes from our dispatcher processes.
                exit_codes = []
                for d in self.dispatcher.values():
                    exit_codes.extend(d.exit_codes())
                exit_codes = set(exit_codes)
                logger.error(
                    f"Dispatcher processes failed with exit codes {exit_codes}"
                )

                # Stop (with managed = True, to avoid redundant health check).
                self.startup_failure = True
                self.stop(managed=True)

                # Propagate startup failure based on the aggregate exit codes during startup.
                # - RESULT_UNMET_REQUIREMENT if this is the only reason for failure.
                # - RESULT_APPLICATION_ERROR in any other case.
                if len(exit_codes) == 1 and RESULT_UNMET_REQUIREMENT in exit_codes:
                    self.notify_error_callback(
                        settings=self.settings, exit_code=RESULT_UNMET_REQUIREMENT
                    )
                    break
                else:
                    self.notify_error_callback(
                        settings=self.settings, exit_code=RESULT_APPLICATION_ERROR
                    )
                    break

            if all([d.all_ready() for d in self.dispatcher.values()]):
                logger.info("Dispatcher ready")
                self.started = True
                break
            if self.is_cancelled:
                logger.warning("Application startup cancelled")
                break

        logger.debug("Start exit")
        return

    def stop(self, managed=False):

        # Stop any hanging startup.
        self.is_cancelled = True

        # Stop dispatcher(s).
        logger = logging.getLogger("ssf")

        logger.debug("Stop enter")

        # Only stop once.
        if self.stopped:
            logger.debug("Stop exit (already stopped)")
            return
        self.stopped = True

        # Wake up watchdog with period 0 so it exits asap.
        self.watchdog_period = 0
        # self.watchdog_wake.acquire()
        # self.watchdog_wake.notify()
        # self.watchdog_wake.release()
        logger.debug("Watchdog join")
        self.watchdog_thread.join()

        # Trailing health check to pick up errors before exit.
        if not managed:
            logger.debug("Final dispatcher health check")
            self.check_dispatcher_health()

        logger.debug("Stopping dispatched processes")
        # Tell the dispatcher process we are stopping.
        [d.stop() for d in self.dispatcher.values()]
        # Kill dispatcher processes (if stop didn't work!)
        [
            dispatcher_process.kill()
            for dispatcher_list in self.dispatcher.values()
            for dispatcher_process in dispatcher_list.processes
            if dispatcher_process is not None
        ]
        logger.debug("Stop exit")

        return

    def get_applications_ids(self):
        return [ssf_config.application.id for ssf_config in self.ssf_config_list]
