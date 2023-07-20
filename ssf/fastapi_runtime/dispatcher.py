# Copyright (c) 2022 Graphcore Ltd. All rights reserved.
import logging
import multiprocessing as mp
import os
import threading
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from queue import Empty as QueueEmpty
from statistics import mean
from threading import Thread
from typing import Dict, List

from common import *
from config import settings

from ssf.application import get_application

from ssf.utils import temporary_cwd
from ssf.config import SSFConfig
from ssf.logger import configure_log_queue
from ssf.logger import get_log_queue


@dataclass
class Dispatcher:
    """Class to hold a single application queue from which to dispatch requests"""

    ctx = mp.get_context("spawn")

    application_id: str
    ssf_config: SSFConfig

    max_restart_reached: bool = False
    max_restart_threshold: int = settings.max_allowed_restarts
    missing = {}

    def __post_init__(self):
        # initialize multiprocessing resources
        ctx = self.ctx
        # Each process is a replica of the same application
        self.processes: List = [None] * settings.replicate_application
        self.input_queue: mp.Queue = ctx.Queue()
        self.output_queue: mp.Queue = ctx.Queue()

        # Global switch to terminate all replica processes
        self.terminate: mp.Event = ctx.Event()

        # Each process is set "ready" after application startup() finishes
        self.ready = [ctx.Event() for _ in range(settings.replicate_application)]

        # A process failure count is incremented after each consecutive failure of application is_healthy()
        # It is reset to 0 as soon as is_healthy() succeeds
        self.process_failure_counts = ctx.Manager().list(
            [0] * settings.replicate_application
        )

        self.log_queue: mp.Queue = get_log_queue()

    def start(self):
        logger = logging.getLogger("ssf")
        logger.debug("Start dispatcher enter")
        if self.log_queue is None:
            raise Exception("Error loading the logger")
        processes = []
        for idx, p in enumerate(self.processes):
            if self.process_failure_counts[idx] >= self.max_restart_threshold:
                self.max_restart_reached = True
                logger.error(
                    f"Dispatcher: Replica {idx} of {self.application_id} health check kept failing after {self.process_failure_counts[idx]} restarts."
                )
            if p is None:
                self.ready[idx].clear()
                process = self.ctx.Process(
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
                logger.debug(f"Starting {self.application_id} replica idx {idx}")
                process.start()
                processes.append(process)
        self.processes = processes
        logger.debug("Start dispatcher exit")

    def stop(self):
        logger = logging.getLogger("ssf")
        logger.debug("Stop dispatcher enter")
        [ready.clear() for ready in self.ready]
        self.terminate.set()
        [p.join() for p in self.processes]
        logger.debug("Stop dispatcher exit")

    def clean(self):
        # return True if all processes are alive
        # remove them otherwise
        logger = logging.getLogger("ssf")
        status = False
        for idx, p in enumerate(self.processes):
            if p and not p.is_alive():
                logger.warning(f"{self.application_id}:{idx} restarted.")
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
        try:
            # redirect process root logger to the queue
            configure_log_queue(log_queue)

            logger = logging.getLogger("ssf_dispatcher")
            logger.info(
                f"Dispatcher started for {self.application_id} [{parent_pid}->{os.getpid()}]"
            )

            # Get instance to serve the endpoint.
            logger.info(f"> Getting user application instance")
            instance = get_application(self.ssf_config)
            app_file_dir = self.ssf_config.application.file_dir

            logger.info(f"instance={instance}")
            logger.info(f"> Running app from {app_file_dir}")

            with temporary_cwd(app_file_dir):
                # Start it up.
                logger.info(f"> Startup user application instance")

                instance.startup()
                healthy = True
                ready.set()

                batching_start, batched_params, batched_meta, thread_ids = (
                    None,
                    [],
                    [],
                    [],
                )
                max_batch_size = self.ssf_config.application.max_batch_size
                # Service the request (queue).
                logger.debug(f"Dispatcher queue processing begin")
                logger.debug(
                    f"Dispatcher settings batching_timeout={settings.batching_timeout} max_batch_size={max_batch_size}"
                )
                call_duration = deque(maxlen=settings.watchdog_request_average)

                while not terminate.is_set() and healthy:
                    try:
                        while (
                            not terminate.is_set()
                            and len(batched_params) != max_batch_size
                        ):

                            if (
                                batching_start
                                and time.time() - batching_start
                                > settings.batching_timeout
                            ):
                                break
                                # self check
                            if not instance.is_healthy():
                                healthy = False
                                raise Exception("Dispatcher health check failed.")

                            # NOTE:
                            # This uses a timeout after 1 second so we can gracefully check for termination.
                            # We need to check that this doesn't add measurable latency for the scenario
                            # where we have intermittent requests.
                            thread_id, inputs = input_queue.get(timeout=1)
                            batching_start = (
                                time.time() if not batching_start else batching_start
                            )
                            params, meta = inputs[:2]

                            batched_params.append(params)
                            batched_meta.append(meta)
                            thread_ids.append(thread_id)

                        logger.debug(
                            f"Dispatcher issuing request with params={batched_params} meta={meta}"
                        )

                        chrono_start = time.time()
                        input = (
                            (batched_params, batched_meta)
                            if max_batch_size > 1
                            else (batched_params[0], batched_meta[0])
                        )
                        results = instance.request(*input)
                        chrono = time.time() - chrono_start

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

                        if settings.watchdog_request_threshold:
                            call_duration.append(chrono)
                        if (
                            len(call_duration) == settings.watchdog_request_average
                            and mean(call_duration)
                            > settings.watchdog_request_threshold
                        ):
                            logger.warning(
                                f"Dispatcher duration watchdog triggered (avg {mean(call_duration)})."
                            )
                            break

                    except QueueEmpty:
                        pass
                    except KeyboardInterrupt:
                        pass
                    # a successful iteration reset the failure loop
                    # detection
                    self.process_failure_counts[index] = 0

        except Exception as e:
            logger.error(f"Dispatcher Exception: {e}")
            self.process_failure_counts[index] += 1
            logger.info(self.process_failure_counts)

        logger.debug("Dispatcher queue processing end")
        ready.clear()

        # Shut it down.
        logger.info(f"> Shutdown user application instance")
        try:
            instance.shutdown()
        except Exception as e:
            logger.error(f"Error in app shutdown: {e}")

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
            if p and p.is_alive() and self.ready[idx].is_set():
                return True

    def all_ready(self):
        # True if all replicas are up and ready
        for idx, p in enumerate(self.processes):
            if not p.is_alive():
                return False
            if not self.ready[idx].is_set():
                return False
        return True

    def all_alive(self):
        # True if all replica processes are alive
        return all(p.is_alive() for p in self.processes)


@dataclass
class Applications:
    """Class to hold the running application(s)"""

    # List of applications declared as config files.
    ssf_config_list: List[str]

    # Each application has a dispatcher (keyed on application id).
    dispatcher: Dict[str, Dispatcher] = field(default_factory=dict)
    watchdog_period: int = 10
    is_cancelled: bool = False
    started = False
    startup_failure = False

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

    def watchdog(self):
        # Watchdog thread.
        # Restart dead workers
        logger = logging.getLogger("ssf")
        logger.debug("Watchdog enter")
        # self.watchdog_wake.acquire()
        while self.watchdog_period:
            for d in self.dispatcher.values():
                if d.clean():
                    d.start()
            # self.watchdog_wake.wait(self.watchdog_period)
            time.sleep(self.watchdog_period)
        logger.debug("Watchdog exit")

    def start(self):
        # Initiate and start dispatcher(s).
        logger = logging.getLogger("ssf")
        logger.debug("Start enter")
        for ssf_config in self.ssf_config_list:
            application_id = ssf_config.application.id
            self.dispatcher.update(
                {
                    application_id: Dispatcher(
                        application_id=application_id,
                        ssf_config=ssf_config,
                    )
                }
            )
            self.dispatcher[application_id].start()
            # self.watchdog_wake = threading.Condition()
            self.watchdog_thread = Thread(target=self.watchdog)
            self.watchdog_thread.start()
            # Wait for workers to be ready
            # If a replica process fails to start,
            # just qui with an error
            while True:
                time.sleep(1)
                if not all([d.all_alive() for d in self.dispatcher.values()]):
                    logger.error(
                        f"Dispatcher failed to start for application {application_id}"
                    )
                    self.startup_failure = True
                    self.stop()
                    raise Exception("Applications Start Failed")
                if all([d.all_ready() for d in self.dispatcher.values()]):
                    logger.info("Dispatcher ready")
                    self.started = True
                    break
                if self.is_cancelled:
                    logger.warning("Applications startup cancelled")
                    break

            logger.debug("Start exit")
        return

    def stop(self):
        # Stop any hanging startup.
        self.is_cancelled = True
        # Stop dispatcher(s).
        logger = logging.getLogger("ssf")
        logger.debug("Stop enter")
        # Wake up watchdog with period 0 so it exits asap.
        self.watchdog_period = 0
        # self.watchdog_wake.acquire()
        # self.watchdog_wake.notify()
        # self.watchdog_wake.release()
        self.watchdog_thread.join()
        # Tell the dispatcher process we are stopping.
        [d.stop() for d in self.dispatcher.values()]
        # Kill dispatcher processes (if stop didn't work!)
        [
            dispatcher_process.kill()
            for dispatcher_list in self.dispatcher.values()
            for dispatcher_process in dispatcher_list.processes
        ]
        logger.debug("Stop exit")
        return
