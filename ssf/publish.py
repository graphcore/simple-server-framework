# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
from typing import List

from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import *

from ssf.utils import logged_subprocess
from ssf.version import VERSION
from ssf.package import get_package_name_and_tag
from shutil import rmtree

logger = logging.getLogger("ssf")

DOCKER_CFG_PATH = ".ssf.docker.config"


def docker_logout_command(ssf_config: SSFConfig):
    args = ssf_config.args
    cmd = ["docker", "--config", DOCKER_CFG_PATH, "logout"]
    server = "DockerHub"
    if args.container_server:
        cmd.append(args.container_server)
        server = args.container_server
    return server, cmd


def docker_login_command(ssf_config: SSFConfig):
    args = ssf_config.args

    assert args.docker_username and args.docker_password
    cmd = [
        "docker",
        "--config",
        DOCKER_CFG_PATH,
        "login",
        "--password-stdin",
        f"--username={args.docker_username}",
    ]
    server = "DockerHub"
    if args.container_server:
        cmd.append(args.container_server)
        server = args.container_server

    return server, cmd, args.docker_password.encode(), DOCKER_CFG_PATH


def publish(ssf_config: SSFConfig):
    logger.info("> ==== Publish ====")

    # Publishing just pushes the docker image.
    # Currently, the bundle is not 'published' anywhere.

    args = ssf_config.args
    config_cmd = []
    assert not ("deploy" in args.commands and not args.deploy_package)

    _, package_tag = get_package_name_and_tag(ssf_config)
    if args.docker_username and args.docker_password:
        server, cmd, pwd, config_file = docker_login_command(ssf_config)
        # checkpoint the current user Docker config
        exit_code = logged_subprocess(f"Login {server}", cmd, piped_input=pwd)
        if exit_code:
            raise SSFExceptionDockerServerError(
                f"Login to {server} errored ({exit_code})"
            )
        config_cmd = ["--config", config_file]

    # With logging INFO for feedback (pushing can take some time).
    logger.info(f"> Pushing container {package_tag}")
    exit_code = logged_subprocess(
        f"Push {package_tag}",
        ["docker", *config_cmd, "push", package_tag],
        stdout_log_level=logging.INFO,
        stderr_log_level=logging.INFO,
    )
    if exit_code:
        raise SSFExceptionDockerServerError(f"Push {package_tag} errored ({exit_code})")
    if args.docker_username and args.docker_password:
        server, cmd = docker_logout_command(ssf_config)
        exit_code = logged_subprocess(f"Logout {server}", cmd)
        if exit_code:
            raise SSFExceptionDockerServerError(
                f"Logout from {server} errored ({exit_code})"
            )
        rmtree(DOCKER_CFG_PATH)
    return RESULT_OK
