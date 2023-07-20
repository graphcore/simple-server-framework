# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
from typing import List, Tuple
from ssf.package import get_package_name_and_tag
from ssf.config import SSFConfig
from ssf.results import *
from ssf.deploy_gcore import deploy as deploy_gcore
from ssf.version import SSF_DEPLOY_IMAGE

logger = logging.getLogger("ssf")

platforms = {
    "Gcore": deploy_gcore,
}


def get_container_options(
    ssf_config: SSFConfig,
) -> Tuple[List[str], List[Tuple[str, str]], int]:
    # For deployment from container image, we can pass run-time SSF options through
    # environment variable SSF_OPTIONS. Build the SSF_OPTIONS from selective arguments
    # for this current call to SSF:
    ssf_options = []
    add_env = []

    args = ssf_config.args

    if args.add_ssh_key:
        for key in args.add_ssh_key:
            ssf_options.append(f"--add-ssh-key {key}")
            add_env.append((key, os.getenv(key)))

    if args.host:
        ssf_options.append(f"--host {args.host}")

    if args.port:
        ssf_options.append(f"--port {args.port}")

    if args.replicate_application:
        ssf_options.append(f"--replicate-application {args.replicate_application}")

    if args.replicate_server:
        ssf_options.append(f"--replicate-server {args.replicate_server}")

    if args.key:
        ssf_options.append(f"--key {args.key}")

    if args.file_log_level:
        ssf_options.append(f"--file-log-level {args.file_log_level}")

    if args.stdout_log_level:
        ssf_options.append(f"--stdout-log-level {args.stdout_log_level}")

    if not args.deploy_package:
        ssf_options.append(f"--config {args.config}")
        ssf_options.extend(["init", "build", "run"])

    return ssf_options, add_env, ssf_config.application.total_ipus


def deploy(ssf_config: SSFConfig):
    logger.info("> ==== Deploy ====")

    platform = ssf_config.args.deploy_platform

    if not platform in platforms:
        raise ValueError(
            f"Deployment platform {platform} is not supported (supported == {platform.keys()})"
        )

    # TODO:
    # Assumes package has been published.
    # Make some checks and warn if it doesn't look right.

    if ssf_config.args.deploy_package:
        _, package_tag = get_package_name_and_tag(ssf_config)
        logger.info(f"Deploy package : package_tag {package_tag}")
    else:
        _, package_tag = get_package_name_and_tag(ssf_config, app_default=False)
        if package_tag:
            logger.info(f"Deploy SSF container : package_tag {package_tag}")
        else:
            package_tag = SSF_DEPLOY_IMAGE
            logger.info(f"Deploy SSF container : package_tag {package_tag} (defaulted)")

    application_id = ssf_config.application.id

    if ssf_config.args.deploy_name:
        name = ssf_config.args.deploy_name
    else:
        name = application_id

    ssf_options, add_env, total_application_ipus = get_container_options(ssf_config)

    return platforms[platform](
        ssf_config,
        application_id,
        package_tag,
        name,
        ssf_options,
        add_env,
        total_application_ipus,
    )
