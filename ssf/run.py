# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import tempfile

from ssf.fastapi_runtime.ssf_run import run as ssf_run_fastapi
from ssf.grpc_runtime.ssf_run import run as ssf_run_grpc
from ssf.results import *
from ssf.utils import (
    API_FASTAPI,
    API_GRPC,
    get_default_ipaddr,
    get_poplar_requirement,
    get_supported_apis,
    poplar_version_ok,
    object_to_ascii,
)

logger = logging.getLogger("ssf")


def run(ssf_config: dict):
    logger.info("> ==== Run ====")

    api = ssf_config.args.api

    if not poplar_version_ok(ssf_config):
        raise SSFExceptionUnmetRequirement(
            f"Missing or unsupported Poplar version - needs {get_poplar_requirement(ssf_config)}"
        )

    supported = get_supported_apis()

    if not api in supported:
        raise SSFExceptionUnmetRequirement(
            f"api {api} is not supported (supported == {supported})"
        )

    ssf_config_file = ssf_config.config_file

    logger.info(f"> Starting {api} runtime with {ssf_config_file}")

    ipaddr = get_default_ipaddr()

    if ipaddr:
        logger.info(f"> Address {ipaddr}:{ssf_config.args.port}")

    result = RESULT_OK

    # Result file for server exit code.
    with tempfile.NamedTemporaryFile() as rf:
        logger.debug(f"result file {rf.name}")
        os.environ["SSF_RESULT_FILE"] = rf.name

        # This is a snapshot of our ssf_config for the runtime process.
        os.environ["SSF_CONFIG"] = object_to_ascii(ssf_config)

        if ssf_config.args.api == API_GRPC:
            ssf_run_grpc(ssf_config.args)
        elif ssf_config.args.api == API_FASTAPI:
            ssf_run_fastapi(ssf_config.args)
        else:
            raise SSFExceptionInternalError()

        errors = set()
        rf.seek(0)
        pid_results = rf.readlines()
        for r in pid_results:
            r = r.decode("ascii")
            pid, result_code = r.strip().split(":")
            result_code = int(result_code)
            logger.debug(f"Error captured for {pid}:{result_code}")
            errors.add(result_code)
        logger.info(f"> Accumulated errors {errors}")

        # We only deal with errors.
        if RESULT_OK in errors:
            errors.remove(RESULT_OK)
        if len(errors) == 1:
            # Return any other single result code (e.g. RESULT_UNMET_REQUIREMENT)
            (result,) = errors
        elif len(errors) > 1:
            # Return RESULT_APPLICATION_ERROR if multiple reasons for failures.
            result = RESULT_APPLICATION_ERROR

    logger.info(f"> Run result {result} {result_to_string(result)}")
    return result
