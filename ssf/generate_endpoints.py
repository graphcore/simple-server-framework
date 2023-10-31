# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os

from .utils import get_supported_apis, load_module, get_endpoints_gen_module_path
from .config import SSFConfig

from ssf.results import SSFExceptionFrameworkResourceError

logger = logging.getLogger("ssf")


def generate_endpoints(ssf_config: SSFConfig):

    supported = get_supported_apis()

    if not ssf_config.args.api in supported:
        raise SSFExceptionFrameworkResourceError(
            f"api {ssf_config.args.api} is not supported (supported == {supported})"
        )

    for endpoint in ssf_config.endpoints:
        endpoint_file = endpoint.file
        generate = endpoint.generate
        idx = endpoint.index

        if generate:
            logger.debug(f"Generating endpoint file {endpoint_file}")
            generate_module = load_module(
                get_endpoints_gen_module_path(ssf_config.args.api), "generate_endpoints"
            )
            generate_module.generate(ssf_config, idx, endpoint_file)
        else:
            if os.path.exists(get_endpoints_gen_module_path(ssf_config.args.api)):
                logger.debug(
                    f"Generating endpoints skipped for custom endpoint file {endpoint_file}"
                )
            else:
                logger.debug(
                    f"Generating endpoints not needed for {ssf_config.args.api} api."
                )


def clean_endpoints(ssf_config: SSFConfig):

    supported = get_supported_apis()

    if not ssf_config.args.api in supported:
        raise SSFExceptionFrameworkResourceError(
            f"api {ssf_config.args.api} is not supported (supported == {supported})"
        )

    for endpoint in ssf_config.endpoints:
        endpoint_file = endpoint.file
        generate = endpoint.generate

        if generate:
            logger.debug(f"Cleaning endpoint file {endpoint_file}")
            if os.path.isfile(endpoint_file):
                os.remove(endpoint_file)
        else:
            if os.path.exists(get_endpoints_gen_module_path(ssf_config.args.api)):
                logger.debug(
                    f"Cleaning endpoints skipped for custom endpoint file {endpoint_file}"
                )
