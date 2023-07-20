# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import uvicorn

from .common import SSFException

logger = logging.getLogger("ssf")


def run(ssf_config_file: str, args):

    # Register the application(s) (configs) to a context
    # for the FastAPI app to reference.
    #
    # NOTES:
    # uvicorn requires that we run from the server directory
    # so we use the app_dir to switch. The ssf_context module
    # is loaded here with explicit id. This ensures that the
    # same ssf_context can be accessed from the server module.

    app_dir = str(os.path.dirname(os.path.abspath(__file__)))

    logger.info(f"> Running Uvicorn")

    # Set current PID so we can tell if uvicorn runs its own processes.
    os.environ["ROOT_PID"] = str(os.getpid())

    # Set config_file in environment for server to pickup in its own process space.
    os.environ["SSF_CONFIG_FILE"] = ssf_config_file

    # Pass through API_KEY from CLI.
    if args.key is not None:
        os.environ["API_KEY"] = args.key

    # Pass through logging levels.
    os.environ["FILE_LOG_LEVEL"] = args.file_log_level
    os.environ["STDOUT_LOG_LEVEL"] = args.stdout_log_level

    # Dispatcher replication.
    os.environ["REPLICATE_APPLICATION"] = str(args.replicate_application)

    # Watchdog setting.
    os.environ["WATCHDOG_REQUEST_THRESHOLD"] = str(args.watchdog_request_threshold)
    os.environ["WATCHDOG_REQUEST_AVERAGE"] = str(args.watchdog_request_average)
    os.environ["MAX_ALLOWED_RESTARTS"] = str(args.max_allowed_restarts)

    # Batching
    os.environ["BATCHING_TIMEOUT"] = str(args.batching_timeout)

    try:
        uvicorn.run(
            "server:app",
            app_dir=app_dir,
            host=args.host,
            port=args.port,
            workers=args.replicate_server,
            log_config=None,
        )
    except SSFException as e:
        logger.error(e)
        return 1
    except BaseException:
        # To surface uvicorn exceptions.
        logger.exception("Uvicorn exception")
        return 1

    return 0
