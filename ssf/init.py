# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os

from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import *
from ssf.generate_endpoints import clean_endpoints
from ssf.utils import temporary_cwd, build_file_list
from ssf.app_venv import destroy_app_venv

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

        # Since this is destructive we prefer safety over convenience:
        # - Glob recursion is disabled.
        # - The user must explicitly specify each/all directories their artifacts fall in.
        _, _, files = build_file_list(
            "./",
            artifacts,
            warn_on_empty_exclusions=False,
            warn_on_empty_inclusions=False,
            glob_recursion=False,
        )

        # Move each found file to the destination with relative path from src_dir.
        for src in files:
            logger.info(f"Clean {src}")
            os.remove(src)

    # Delete application venv
    destroy_app_venv(ssf_config)

    return RESULT_OK
