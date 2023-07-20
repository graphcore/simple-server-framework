# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import typing

from .generate_endpoints_fastapi import generate as generate_endpoints_fastapi
from .config import SSFConfig

logger = logging.getLogger("ssf")


def generate_endpoints(ssf_config: SSFConfig):

    supported = [
        "fastapi",
    ]

    if not ssf_config.args.api in supported:
        raise ValueError(
            f"api {ssf_config.args.api} is not supported (supported == {supported})"
        )

    for endpoint in ssf_config.endpoints:
        endpoint_file = endpoint.file
        generate = endpoint.generate
        idx = endpoint.index

        if generate:
            logger.debug(f"Generating endpoint file {endpoint_file}")
            generate_endpoints_fastapi(ssf_config, idx, endpoint_file)
        else:
            logger.debug(
                f"Generating endpoints skipped for custom endpoint file {endpoint_file}"
            )


def clean_endpoints(ssf_config: SSFConfig):

    supported = [
        "fastapi",
    ]

    if not ssf_config.args.api in supported:
        raise ValueError(
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
            logger.debug(
                f"Cleaning endpoints skipped for custom endpoint file {endpoint_file}"
            )
