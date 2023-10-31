# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# The notify_error_callback is used to receive notification that the application has errored.
# If the result_file has been specified then write out a result_code to file.
# This is used to circumvent Uvicorn exit codes which are not always useful and to
# accumulate result codes where multiple server processes might be used or just record
# the occurence in any case.
# Writing result code for this process as "<pid>:<code>", which should be
# safe for multiple server replicas on Linux.
# The secondary setting.stop_on_error is used to decide whether to silently fail
# (leaving the health probes running) or to immediately stop serving.

import logging
import os
import signal
from ssf.common_runtime.config import Settings

from ssf.results import RESULT_APPLICATION_ERROR

logger = logging.getLogger()


def notify_error_callback(settings: Settings, exit_code=RESULT_APPLICATION_ERROR):
    logger.error(f"Application has errored : {exit_code}")
    if settings.result_file:
        with open(settings.result_file, "a") as result_file:
            record = f"{os.getpid()}:{exit_code}"
            logger.error(f"Recorded error {record}")
            result_file.write(record + "\n")
    if settings.stop_on_error:
        logger.warning(f"> Stopping server")
        os.kill(os.getpid(), signal.SIGINT)
