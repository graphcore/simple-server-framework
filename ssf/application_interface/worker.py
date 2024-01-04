# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# NOTE:
# Do not import external packages in application_interface modules
# to avoid introducing additional dependencies for the application.
# Only import SSF modules that are also in application_interface.

import multiprocessing
import multiprocessing.managers
import signal
import logging
import time
import sys
import os
from queue import Empty as QueueEmpty
from collections import deque
from statistics import mean

# add ssf root path
sys.path.insert(
    0,
    os.path.realpath(os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))),
)

from ssf.application_interface.runtime_settings import *
from ssf.application_interface.application import get_application
from ssf.application_interface.results import *
from ssf.application_interface.config import SSFConfig
from ssf.application_interface.logger import configure_log_queue
from ssf.application_interface.utils import ReplicaManager, temporary_cwd


def sigint_handler(signal, frame):
    # Worker will ignore SIGINT to exit gracefully
    pass


def add_app_extra_paths(ssf_config):
    def add_sys_path(path: str):
        if path not in sys.path:
            sys.path.insert(0, path)

    add_sys_path(ssf_config.application.dir)
    add_sys_path(ssf_config.application.file_dir)
    if ssf_config.application.syspaths:
        for p in reversed(ssf_config.application.syspaths):
            p = os.path.abspath(os.path.join(ssf_config.application.dir, p))
            add_sys_path(p)


def process_loop(
    ssf_config: SSFConfig,
    settings: Settings,
    parent_pid: int,
    process_failure_counts: list,
    input_queue: multiprocessing.Queue,
    output_queue: multiprocessing.Queue,
    ready: multiprocessing.Event,
    terminate: multiprocessing.Event,
    log_queue: multiprocessing.Queue,
    index: int,
):
    exit_code = 0
    thread_ids = []

    try:
        signal.signal(signal.SIGINT, sigint_handler)
        add_app_extra_paths(ssf_config)
        configure_log_queue(log_queue)
        # redirect process root logger to the queue
        logger = logging.getLogger("Worker")
        logger.info(
            f"> [{index}] Worker started for {ssf_config.application.id}, [{parent_pid}->{os.getpid()}]"
        )
        # Get instance to serve the endpoint.
        logger.info(f"> [{index}] Getting user application instance")
        instance = get_application(ssf_config)
        app_file_dir = ssf_config.application.file_dir

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
                if settings.watchdog_ready_period > 0:
                    last_ready_watchdog = time.time()

            reset_watchdog_ready_period()

            batching_start, batched_params, batched_meta = (None, [], [])
            max_batch_size = ssf_config.application.max_batch_size
            # Service the request (queue).
            logger.debug(f"[{index}] Dispatcher queue processing begin")
            logger.debug(
                f"[{index}] Dispatcher settings batching_timeout={settings.batching_timeout} max_batch_size={max_batch_size}"
            )
            call_duration = deque(maxlen=settings.watchdog_request_average)

            while not terminate.is_set() and healthy:
                try:
                    while (
                        not terminate.is_set() and len(batched_params) != max_batch_size
                    ):
                        now = time.time()

                        if (
                            batching_start
                            and now - batching_start > settings.batching_timeout
                        ):
                            break

                        if (
                            last_ready_watchdog is not None
                            and (now - last_ready_watchdog)
                            > settings.watchdog_ready_period
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

                    if settings.watchdog_request_threshold:
                        call_duration.append(chrono)
                    if (
                        len(call_duration) == settings.watchdog_request_average
                        and mean(call_duration) > settings.watchdog_request_threshold
                    ):
                        logger.warning(
                            f"[{index}] Dispatcher duration watchdog triggered (avg {mean(call_duration)})."
                        )
                        break

                    # A successful request =>
                    # - reset the failure loop detection
                    # - reset period until next watchdog ready poll
                    process_failure_counts[index] = 0
                    reset_watchdog_ready_period()

                except QueueEmpty:
                    pass
                except KeyboardInterrupt:
                    # Should never be the case (SIGINT handled)
                    pass

    except Exception as e:
        logger.exception(e)
        process_failure_counts[index] += 1
        logger.info(
            f"[{index}] Application instance failure counts: {process_failure_counts}"
        )
        for t_id in thread_ids:
            output_queue.put((t_id, None))
        if isinstance(e, SSFException):
            exit_code = e.result_code
        else:
            exit_code = RESULT_APPLICATION_ERROR

    try:
        if process_failure_counts:
            logger.info(f"[{index}] Failure count {process_failure_counts}")

        logger.debug(f"[{index}] Dispatcher queue processing end")
        ready.clear()

        # Shut it down.
        logger.info(f"> [{index}] Shutdown user application instance")

        instance.shutdown()
    except Exception as e:
        logger.exception(e)

    sys.exit(exit_code)


def just_build_app(ssf_config, log_queue, parent_pid):
    try:

        add_app_extra_paths(ssf_config)
        configure_log_queue(log_queue)
        # redirect process root logger to the queue
        logger = logging.getLogger("Build")
        logger.info(
            f">  Builder process started for {ssf_config.application.id} [{os.getpid()}]"
        )
        # Get instance to serve the endpoint.
        logger.info(f"> [{index}] Getting user application instance")
        instance = get_application(ssf_config)
        app_file_dir = ssf_config.application.file_dir
        logger.info(f"> [{index}] Running app from {app_file_dir}")
        logger.info(f"instance={instance}")
        logger.info("> Build application")

        # Where the user's application sources are.
        app_file_dir = ssf_config.application.file_dir

        # Run build from application module file directory
        with temporary_cwd(app_file_dir):
            ret = instance.build()
            instance.shutdown()
        return ret

    except SSFException as e:
        logger.exception(e)
        sys.exit(e.result_code)


def make_worker_manager(port, address, auth_key, index):
    port = int(port)
    manager = ReplicaManager(address=(address, port), authkey=auth_key)
    manager.register("input_queue")
    manager.register("output_queue")
    manager.register("log_queue")
    manager.register("ready")
    manager.register("terminate")
    manager.register("failure_count")
    manager.register("config")
    manager.register(f"ready_{index}")
    manager.connect()
    return manager


def make_minimal_manager(port, address, auth_key):
    port = int(port)
    manager = ReplicaManager(address=(address, port), authkey=auth_key)
    manager.register("log_queue")
    manager.register("config")
    manager.connect()
    return manager


if __name__ == "__main__":

    assert (
        len(sys.argv) == 3
    ), "Error: worker only supports 2 arguments (replica_index, port)"
    index = int(sys.argv[1])
    port = int(sys.argv[2])

    if index >= 0:
        # start an actual worker
        manager = make_worker_manager(int(port), "localhost", b"ssf", index)
        process_loop(
            ssf_config=manager.config().get("ssf_config"),
            settings=manager.config().get("settings"),
            parent_pid=manager.config().get("server_pid"),
            process_failure_counts=manager.failure_count(),
            input_queue=manager.input_queue(),
            output_queue=manager.output_queue(),
            ready=manager.__getattribute__(f"ready_{index}")(),
            terminate=manager.terminate(),
            log_queue=manager.log_queue(),
            index=index,
        )
    else:
        # just run the build step
        manager = make_minimal_manager(port, "localhost", b"ssf")
        ret = just_build_app(
            ssf_config=manager.config().get("ssf_config"),
            log_queue=manager.log_queue(),
            parent_pid=manager.config().get("server_pid"),
        )
        sys.exit(ret)
