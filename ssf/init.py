# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import importlib
import logging
import os
import typing

from ssf.generate_endpoints import clean_endpoints
from ssf.utils import temporary_cwd, build_file_list
from ssf.results import *

from .config import SSFConfig

logger = logging.getLogger("ssf")


def init(ssf_config: SSFConfig):
    logger.info("> ==== Init ====")

    logger.info("> Cleaning endpoints")
    clean_endpoints(ssf_config)

    logger.info("> Cleaning application")

    # Where the user's application sources are.
    app_dir = ssf_config.application.dir

    # Run clean from application directory
    with temporary_cwd(app_dir):
        # This uses the artifacts decls in the ssf_config.
        artifacts = ssf_config.application.artifacts

        _, _, files = build_file_list("./", artifacts)

        # Move each found file to the destination with relative path from src_dir.
        for src in files:
            logger.info(f"Clean {src}")
            os.remove(src)

    return RESULT_OK
