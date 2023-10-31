# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import uvicorn

from ssf.results import SSFExceptionUvicornError

logger = logging.getLogger("ssf")


def run(args):

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

    try:
        uvicorn.run(
            "server:app",
            app_dir=app_dir,
            host=args.host,
            port=args.port,
            workers=args.fastapi_replicate_server,
            log_config=None,
        )
    except BaseException as e:
        raise SSFExceptionUvicornError from e
