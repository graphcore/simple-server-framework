# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import sys

from ssf.config import SSFConfig
from ssf.application import get_application
from ssf.fastapi_runtime.ssf_run import run as ssf_run_fastapi
from ssf.utils import (
    get_default_ipaddr,
    poplar_version_ok,
    get_poplar_requirement,
)
from ssf.results import *


logger = logging.getLogger("ssf")


def run(ssf_config: SSFConfig):
    logger.info("> ==== Run ====")

    api = ssf_config.args.api

    if not poplar_version_ok(ssf_config):
        logger.warning(
            f"Skip due to missing or unsupported Poplar version - needs {get_poplar_requirement(ssf_config)}"
        )
        return RESULT_SKIPPED

    supported = [
        "fastapi",
    ]

    if not api in supported:
        raise ValueError(f"api {api} is not supported (supported == {supported})")

    ssf_config_file = ssf_config.config_file

    logger.info(f"> Starting {api} runtime with {ssf_config_file}")

    ipaddr = get_default_ipaddr()
    if ipaddr:
        logger.info(f"> Address {ipaddr}:{ssf_config.args.port}")

    if api == "fastapi":
        ret = ssf_run_fastapi(ssf_config_file, ssf_config.args)
        return ret

    return RESULT_SKIPPED
