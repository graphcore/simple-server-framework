# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import importlib
import logging
import os
import typing

from ssf.generate_endpoints import generate_endpoints
from ssf.application import get_application, clear_application
from ssf.utils import temporary_cwd, poplar_version_ok, get_poplar_requirement
from ssf.results import *

from .config import SSFConfig


logger = logging.getLogger("ssf")


def build(ssf_config: SSFConfig):
    logger.info("> ==== Build ====")

    if not poplar_version_ok(ssf_config):
        logger.warning(
            f"Skip due to missing or unsupported Poplar version - needs {get_poplar_requirement(ssf_config)}"
        )
        return RESULT_SKIPPED

    logger.info("> Generate_endpoints")
    generate_endpoints(ssf_config)

    logger.info(f"> Load application")

    application = get_application(ssf_config)
    logger.info(f"instance={application}")

    logger.info("> Build application")

    # Where the user's application sources are.
    app_file_dir = ssf_config.application.file_dir

    # Run build from application module file directory
    with temporary_cwd(app_file_dir):
        ret = application.build()
        # Application instance will not be used further, delete it
        application.shutdown()

    clear_application(ssf_config)

    return ret
