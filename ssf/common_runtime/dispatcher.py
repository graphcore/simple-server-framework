# Copyright (c) 2022 Graphcore Ltd. All rights reserved.
import logging
import multiprocessing as mp
import subprocess
from socket import socket
from multiprocessing.managers import ListProxy
import os
import threading
import time
from dataclasses import dataclass, field
from threading import Thread
from typing import Dict, List, Union
from functools import partial

from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import *
from ssf.application_interface.logger import get_log_queue
from ssf.application_interface.runtime_settings import Settings

from ssf.utils import ReplicaManager
from ssf.sdk_utils import maybe_activate_poplar_sdk
from ssf.common_runtime.common import *


class WorkerProcess:
    """Class to manage a single worker process"""

    def __init__(self, index: int, port: int, executable: str, env):
        self.index = index
        self.port = port
        self.executable = executable
        self.process = None
        self.pid = None
        self.env = env

    def start(self):
        this_path = os.path.dirname(os.path.abspath(__file__))
        worker_pth = os.path.realpath(
            os.path.join(this_path, "../application_interface/worker.py")
        )

        self.process = subprocess.Popen(
            [self.executable, worker_pth, str(self.index), str(self.port)], env=self.env
        )
        self.pid = self.process.pid

    def is_alive(self):
        return self.process.poll() is None

    def join(self):
        self.process.wait()

    @property
    def exitcode(self):
        return self.process.returncode

    def close(self):
        pass


# Global function to make "frozen" picklable callables
def get_attr(obj):
    return obj


@dataclass
class Dispatcher:
    """Class to hold a single application queue from which to dispatch requests"""

    settings: Settings
    application_id: str
    ssf_config: SSFConfig
    max_restart_reached: bool = False
    missing = {}

    def __post_init__(self):
        self.env = maybe_activate_poplar_sdk(self.ssf_config)
        self.max_restart_threshold: int = self.settings.max_allowed_restarts
        # Initialize multiprocessing resources
        # Each worker process is a replica of the same application
        self.processes: List[Union(WorkerProcess, None)] = [
            None
        ] * self.settings.replicate_application
        # SyncManager for replica workers communication
        with socket() as s:
            # Get a free port from OS
            s.bind(("", 0))
            self.port = s.getsockname()[1]
            self.manager = ReplicaManager(
                address=("localhost", int(self.port)), authkey=b"ssf"
            )
        self.manager.register("input_queue", callable=partial(get_attr, mp.Queue()))
        self.manager.register("output_queue", callable=partial(get_attr, mp.Queue()))
        self.manager.register("log_queue", callable=partial(get_attr, get_log_queue()))
        self.manager.register("terminate", callable=partial(get_attr, mp.Event()))
        self.manager.register(
            "failure_count",
            callable=partial(get_attr, [0] * self.settings.replicate_application),
            proxytype=ListProxy,
        )
        self.manager.register(
            "config",
            callable=partial(
                get_attr,
                {
                    "ssf_config": self.ssf_config,
                    "settings": self.settings,
                    "server_pid": os.getpid(),
                },
            ),
        )
        for k in range(self.settings.replicate_application):
            self.manager.register(f"ready_{k}", callable=partial(get_attr, mp.Event()))
        self.manager.start()
        logger = logging.getLogger("ssf")
        logger.debug(f"Resource manager PID: {self.manager._process.ident}")

    @property
    def process_failure_counts(self) -> List[int]:
        """A process failure_count is incremented after each consecutive failure of application process.
        It is reset to 0 as soon as the application process is running successfully."""
        return self.manager.failure_count()

    @property
    def ready(self) -> List[mp.Event]:
        """Each replica process is set "ready" (using mp.Event) after application startup() finishes"""
        return [
            self.manager.__getattribute__(f"ready_{k}")()
            for k in range(self.settings.replicate_application)
        ]

    @property
    def terminate(self) -> mp.Event:
        """Global switch to terminate all replica processes"""
        return self.manager.terminate()

    @property
    def input_queue(self) -> mp.Queue:
        return self.manager.input_queue()

    @property
    def output_queue(self) -> mp.Queue:
        return self.manager.output_queue()

    @property
    def log_queue(self) -> mp.Queue:
        return self.manager.log_queue()

    def start(self):
        logger = logging.getLogger("ssf")
        logger.debug(f"Start dispatcher enter {self.process_failure_counts}")
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
                new_processes[idx] = WorkerProcess(
                    idx,
                    self.port,
                    os.path.join(self.ssf_config.application.venv_dir, "bin/python"),
                    self.env,
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
        logger = logging.getLogger("ssf")
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
class Application:
    """Class to hold the running application"""

    settings: Settings
    ssf_config: str
    notify_error_callback: callable
    result_code: int = RESULT_OK
    dispatcher: Dispatcher = None
    watchdog_period: int = 10
    is_cancelled: bool = False
    started = False
    startup_failure = False
    stopped = True

    def is_ready(self):
        if self.started:
            return self.dispatcher.is_ready()
        else:
            return False

    def is_alive(self):
        if self.started:
            return self.dispatcher.is_alive() and self.watchdog_thread.is_alive()
        else:
            return not self.startup_failure

    def check_dispatcher_health_ok(self):
        if self.dispatcher.clean():
            self.notify_error_callback(settings=self.settings)
            return False
        return True

    def watchdog(self):
        # Watchdog thread.
        # Restart dead workers
        logger = logging.getLogger("ssf")
        logger.debug("Watchdog enter")
        while self.watchdog_period:
            if not self.check_dispatcher_health_ok():
                self.dispatcher.start()
            time.sleep(self.watchdog_period)
        logger.debug("Watchdog exit")

    def start(self):
        # Initiate and start dispatcher(s).
        logger = logging.getLogger("ssf")
        logger.debug("Start enter")
        self.stopped = False

        self.dispatcher = Dispatcher(
            settings=self.settings,
            application_id=self.ssf_config.application.id,
            ssf_config=self.ssf_config,
        )

        self.dispatcher.start()
        self.watchdog_thread = Thread(target=self.watchdog)
        self.watchdog_thread.start()

        # Wait for workers to be ready for this application.
        # If a replica process fails to start,
        # just quit with an error
        while True:
            time.sleep(1)
            if not self.dispatcher.all_alive():
                logger.error(f"Dispatcher failed to start")

                # Get set of unique exit codes from our dispatcher processes.
                exit_codes = []
                exit_codes.extend(self.dispatcher.exit_codes())
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

            if self.dispatcher.all_ready():
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
        logger.debug("Watchdog join")
        self.watchdog_thread.join()

        # Trailing health check to pick up errors before exit.
        if not managed:
            logger.debug("Final dispatcher health check")
            self.check_dispatcher_health_ok()

        logger.debug("Stopping dispatched processes")
        # Tell the dispatcher process we are stopping.
        self.dispatcher.stop()

        # Kill dispatcher processes (if stop didn't work!)
        [
            dispatcher_process.kill()
            for dispatcher_process in self.dispatcher.processes
            if dispatcher_process is not None
        ]

        logger.debug("Stop exit")

        return

    def get_application_id(self):
        return self.ssf_config.application.id
