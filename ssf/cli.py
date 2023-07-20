# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import argparse
from packaging import version
import logging
import os
import sys
from collections import OrderedDict
from typing import Tuple, Optional

sys.path.insert(len(sys.path), os.path.abspath(__file__))

from ssf.init import init as ssf_init
from ssf.build import build as ssf_build
from ssf.run import run as ssf_run
from ssf.package import package as ssf_package
from ssf.test import test as ssf_test
from ssf.publish import publish as ssf_publish
from ssf.deploy import deploy as ssf_deploy
from ssf.utils import expand_str, ipu_count_ok
from ssf.logger import init_global_logging, set_default_logging_levels
from ssf.version import (
    VERSION,
    ID,
    NAME,
    MINIMUM_SUPPORTED_VERSION,
    MAXIMUM_SUPPORTED_VERSION,
    PACKAGE_DEFAULT_BASEIMAGE,
    SSF_DEPLOY_IMAGE,
)
from ssf.repo import clone as repo_clone
from ssf.ssh import add_ssh_key
from ssf.config import SSFConfig
from ssf.load_config import ConfigGenerator
from ssf.results import *

DEFAULT_CONFIG = "ssf_config.yaml"
REPO_ROOT = ".repo"
GRADIENT_MODELS_ROOT = ".gradient-model"


def parse_config(
    repo_config: str, repo_root: str = REPO_ROOT
) -> Tuple[str, str, str, str, str]:
    # Parse a config for repo info
    #
    # ** From local source code **
    #
    # <filename>
    #
    # e.g. ~/myapp/ssf_config.yaml
    #
    # - Or -
    #
    # ** From remote repository **
    #
    # <giturl>{@checkout}|<filename(relative to repository root)>
    #
    # Where {@checkout} is optional and can be a branch or SHA.
    #
    # e.g.
    # git@github.com:graphcore/my_application.git|ssf/ssf_config.yaml
    # git@github.com:graphcore/my_application.git@release|ssf/ssf_config.yaml
    # git@github.com:graphcore/my_application.git@5468e01|ssf/ssf_config.yaml
    #
    # Return:
    #  For e.g. git@github.com:graphcore/my_application.git|ssf/ssf_config.yaml
    #    repo: git@github.com:graphcore/my_application.git
    #    repo_dir: .repo
    #    repo_name: my_application
    #    config: .repo/my_application/ssf/ssf_config.yaml
    #    config_file: ssf/ssf_config.yaml
    #    checkout: None
    #
    # Return:
    #  For e.g. git@github.com:graphcore/my_application.git@release|ssf/ssf_config.yaml
    #    repo: git@github.com:graphcore/my_application.git
    #    repo_dir: .repo
    #    repo_name: my_application
    #    config: .repo/my_application/ssf/ssf_config.yaml
    #    config_file: ssf/ssf_config.yaml
    #    checkout: release
    #
    repo = None
    repo_dir = None
    repo_name = None
    config = None
    config_file = None
    checkout = None
    if ":" in repo_config:
        sep = repo_config.find("|")
        if sep == -1:
            repo = repo_config
            config_file = DEFAULT_CONFIG
        else:
            repo = repo_config[:sep]
            config_file = repo_config[sep + 1 :]

        prefix, repo_dir = os.path.split(repo)
        if repo_dir.find("@") != -1:
            repo_dir, checkout = repo_dir.split("@")
            repo = os.path.join(prefix, repo_dir)
        repo_name, _ = os.path.splitext(repo_dir)
        config = os.path.join(os.path.join(repo_root, repo_name), config_file)
        repo_dir = repo_root
    else:
        config_file = repo_config
        config = os.path.realpath(os.path.expanduser(repo_config))

    return repo, repo_dir, repo_name, config, config_file, checkout


def run(cli_args: list):
    class SmartArgparserFormatter(
        argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter
    ):
        pass

    parser = argparse.ArgumentParser(
        description=f"{NAME} {VERSION}\n\n"
        f"Supports application config ssf_version: {MINIMUM_SUPPORTED_VERSION} - {MAXIMUM_SUPPORTED_VERSION}\n"
        f"Package default base image: {PACKAGE_DEFAULT_BASEIMAGE}\n"
        f"Deploy default SSF image: {SSF_DEPLOY_IMAGE}",
        formatter_class=SmartArgparserFormatter,
    )

    # User must specify one and only one of the primary operations
    # (run, build or package)
    parser.add_argument(
        "commands",
        nargs="*",
        help="Which commands to run.\n"
        "These can be combined but will always run in the sequence described here.\n"
        " \n"
        "For example, to start local serving:\n"
        "$ ssf --config <config> init build run\n"
        " \n"
        "Or to build, publish and deploy:\n"
        "$ ssf --config <config> init build package publish deploy\n"
        " \n"
        "init    - If using remote application then re-clone it; clean artifacts\n"
        "build   - Build the application\n"
        "run     - Run the application\n"
        "package - Package the application (bundle and container image)\n"
        "test    - Test the most recently packaged application container image\n"
        "publish - Push the most recently packaged application container image\n"
        "deploy  - Deploy the application within the SSF container (default), or,\n"
        "          use `--deploy-package` to deploy the most recently packaged and published application container image instead.\n"
        f"          The default SSF image is `{SSF_DEPLOY_IMAGE}`, but this can be overridden with the `--package-tag` argument.\n"
        "          Do not publish and deploy in the same call unless you are also using `--deploy-package` to deploy the application container image.",
    )

    # User can specify a specific yaml otherwise we will
    # assume there is a config named "ssf.yaml" in the CWD
    # TODO:
    # We might consider supporting a list of yamls if the user really
    # wants to combined multiple applications. All of build, run and
    # prepare would need updating to handle this.

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="The SSF configuration (YAML).\n"
        "<filename> : Local application filename (e.g. my_application/ssf/ssf_config.yaml)\n"
        "<giturl>|<filename> : Remote application and filename (e.g. git@github.com:graphcore/my_application.git|ssf/ssf_config.yaml)\n"
        "<giturl> : Remote application, ssf_config will be auto-discovered (e.g. git@github.com:graphcore/my_application.git)\n"
        "It is possible to specify a branch or ref with the giturl. e.g. git@github.com:graphcore/my_application.git@release\n"
        "It is possible to use a local repo with the giturl. e.g. file:///my_application",
    )

    general_opt = parser.add_argument_group("# General options")
    run_opt = parser.add_argument_group("# Runtime (gc-ssf run) options")
    container_opt = parser.add_argument_group(
        "# Container options (package and publish)"
    )
    deploy_opt = parser.add_argument_group("# Deployment (gc-ssf deploy) options")
    test_opt = parser.add_argument_group("# Test (gc-ssf test) options")

    # User can specify which API to generate.
    # Currently this is only REST with FastAPI.
    general_opt.add_argument(
        "-a",
        "--api",
        type=str,
        default="fastapi",
        choices=["fastapi"],
        help="Which API framework to use",
    )

    # User can add an ssh key by specifying one or more
    # environment variables that hold the key.
    general_opt.add_argument(
        "--add-ssh-key",
        type=str,
        default=None,
        action="append",
        help="Add an SSH key (for example for a remote repo).\n"
        "Provide the key in an environment variable and specify the environment variable name with this argument.\n"
        "Multiple keys can be added if necessary. Keys are added before any other commands are processed.",
    )

    # User can override default log levels.
    general_opt.add_argument(
        "--file-log-level",
        type=str,
        default="DEBUG",
        help="Set file log level.",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    general_opt.add_argument(
        "--stdout-log-level",
        type=str,
        default="INFO",
        help="Set stdout log level.",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    # User can specify the host address to bind.
    run_opt.add_argument(
        "--host", type=str, default="0.0.0.0", help="Address to bind to (serve from)"
    )

    # User can specify the host port to bind.
    run_opt.add_argument(
        "-p", "--port", type=int, default=8100, help="Port to bind to (serve from)"
    )

    # User can select replication (of application).
    run_opt.add_argument(
        "-ra",
        "--replicate-application",
        type=int,
        default=1,
        help="Number of application instances",
    )

    # User can select replication (of server).
    run_opt.add_argument(
        "-rs",
        "--replicate-server",
        type=int,
        default=1,
        help="Number of server instances",
    )

    # User can specify an API key.
    run_opt.add_argument(
        "-k", "--key", type=str, default=None, help="Secure the API with an API key."
    )

    # User can set the time threshold for duration watchdog and the rolling window size
    run_opt.add_argument(
        "--watchdog-request-threshold",
        type=float,
        default=0,
        help="Set threshold value in seconds for request duration. If exceeded the watchdog will restart the application.\n"
        "Value set to 0 (default) disables the request duration watchdog.",
    )

    run_opt.add_argument(
        "--watchdog-request-average",
        type=int,
        default=3,
        help="Set number of last requests included in calculating average watchdog request duration.",
    )

    # User can set batching timeout
    run_opt.add_argument(
        "--batching-timeout",
        type=float,
        default=1,
        help="Set how many seconds the server will wait to accumulate samples when batching is enabled.",
    )

    run_opt.add_argument(
        "--max-allowed-restarts",
        type=int,
        default=2,
        help="Number of time a replica can fails successively on restart before going to an irrecoverable error state",
    )

    container_opt.add_argument(
        "--package-baseimage",
        type=str,
        default=None,
        help="Override default baseimage when packaging.\n"
        "The default baseimage is taken from the application config (application.package.docker.baseimage),\n"
        f"or set to {PACKAGE_DEFAULT_BASEIMAGE}. If PACKAGE_BASEIMAGE is specified then it overrides the default baseimage.",
    )

    container_opt.add_argument(
        "--package-name",
        type=str,
        default=None,
        help="Override default bundle name when packaging or publishing.",
    )

    container_opt.add_argument(
        "--package-tag",
        type=str,
        default=None,
        help="Override default image tag when packaging or publishing. \n"
        "Format: --package-tag  user/repo:tag",
    )

    container_opt.add_argument(
        "--docker-username",
        type=str,
        default=None,
        help="Username for login, if login to a docker repository is required when publishing.\n"
        "You can login to your docker server before running SSF if preferred, in which case this argument can be skipped.\n"
        "If login is required, both username and password must be specified, server is optional.\n",
    )

    container_opt.add_argument(
        "--docker-password",
        type=str,
        default=None,
        help="Password for login, if login to a docker repository is required when publishing.\n"
        "You can login to your docker server before running SSF if preferred, in which case this argument can be skipped.\n"
        "If login is required, both username and password must be specified, server is optional.\n",
    )

    container_opt.add_argument(
        "--container-server",
        type=str,
        default=None,
        help="Server for login, if login to a container repository is required when publishing.\n"
        "You can login to your container server before running SSF if preferred, in which case this argument can be skipped.\n"
        "If login is required, both username and password must be specified, server is optional.",
    )

    deploy_opt.add_argument(
        "--deploy-platform",
        type=str,
        default="Gcore",
        choices=[
            "Gcore",
        ],
        help="The target platform for deployment.\n"
        "Gcore deployments start or update a deployment at the specified remote target address using a simple bash boot script and ssh.",
    )

    deploy_opt.add_argument(
        "--deploy-name",
        type=str,
        default=None,
        help="The deployment name (defaults to application ID if not specified).",
    )

    deploy_opt.add_argument(
        "--deploy-package",
        action="store_true",
        help="The default is to deploy an SSF container and dynamically build and run the application from within the SSF container.\n"
        "Use this option to instead deploy the application's pre-packaged and published container.",
    )

    deploy_opt.add_argument(
        "--deploy-gcore-target-username",
        type=str,
        default=None,
        help="Gcore: The target username with which to launch the deployment.",
    )

    deploy_opt.add_argument(
        "--deploy-gcore-target-address",
        type=str,
        default=None,
        help="Gcore: The target address with which to launch the deployment.",
    )

    test_opt.add_argument(
        "--test-skip-stop",
        action="store_true",
        help="Don't stop the application container after running 'test'.",
    )

    test_opt.add_argument(
        "--test-skip-start",
        action="store_true",
        help="Don't start the application container before running 'test' (assume it is already running).",
    )

    # Parse arguments
    try:
        args = parser.parse_args(cli_args)
    except SystemExit:
        if "--help" in cli_args or "-h" in cli_args:
            return RESULT_OK
        return RESULT_BAD_ARG

    # Helper to expand args (replace symbolic references with values from ssf config).
    # To support, e.g,
    #   --package-tag "my-release-repo:{{application.id}}-{{application.version}}-latest"
    def expand_args_from_dict(
        args: argparse.Namespace, ssf_config: Optional[SSFConfig]
    ):
        a = vars(args)
        for k, v in a.items():
            if isinstance(v, str):
                a[k] = expand_str(v, ssf_config)
        args = argparse.Namespace(**a)
        return args

    commands = args.commands

    set_default_logging_levels(args.file_log_level, args.stdout_log_level)
    init_global_logging()
    logger = logging.getLogger()

    # When deploying with the SSF container it is possible to override the
    # default SSF image with --package-tag and in this case the user
    # MUST NOT also publish.
    #
    # In practice, the expected use cases are:
    #
    # Test locally then deploy within SSF container:
    #    gc-ssf ... init build run package test deploy
    #
    #   --OR--
    #
    # Test locally, then publish and deploy published image:
    #    gc-ssf ... --deploy-package init build run package test publish deploy
    #
    if len(set(commands).intersection({"publish", "deploy"})) == 2:
        if not args.deploy_package:
            msg = (
                "Do not attempt to publish the application container image while also deploying within the SSF image. "
                + "Either, use `--deploy-package` to deploy the published application container image (instead of the SSF image), or, remove `publish`"
            )
            logger.error(msg)
            return RESULT_BAD_ARG

    if args.deploy_name and " " in args.deploy_name:
        logger.error("--deploy-name should not contain any space")
        return RESULT_BAD_ARG

    # Add keys if any specified.
    if args.add_ssh_key:
        for key in args.add_ssh_key:
            add_ssh_key(key)

    config = args.config

    if len(commands) == 0:
        exit(0)

    if config is None:
        # Check if we just want to package and/or publish SSF.
        # => Self-containerise (no application module or endpoints).
        if len(set(commands) - {"package", "publish"}) == 0:
            logger.info("> Self-package/publish")
            ssf_config_dict = {
                "ssf_version": VERSION,
                "application": {
                    "id": ID,
                    "name": NAME,
                    "version": VERSION,
                    "package": {
                        "tag": "graphcore/cloudsolutions-dev:{{application.id}}-{{application.version}}"
                    },
                },
            }

            ssf_config = ConfigGenerator(ssf_config_dict, yaml=False).load(
                self_package=True, args=args
            )
            args = expand_args_from_dict(args, ssf_config)
            ssf_config.args = args

            if "package" in commands:
                ret = ssf_package(ssf_config)

            if "publish" in commands:
                ret = ssf_publish(ssf_config)

            exit(0)

        # Else default config.
        config = DEFAULT_CONFIG

    # Get repo/config from --config arg.
    repo, repo_dir, repo_name, config, config_file, checkout = parse_config(config)

    if repo:
        logger.info(f"> Repo {repo}")
        logger.info(f"> Repo dir {repo_dir}")
        logger.info(f"> Repo name {repo_name}")
        logger.info(f"> Config {config}")
        logger.info(f"> Config file {config_file}")
        logger.info(f"> Checkout {checkout}")
    else:
        logger.info(f"> Config {config}")

    # Only clone for 'init'
    if "init" in commands and repo:
        logger.info(f"> Cloning repo")
        repo_clone(repo, repo_dir, repo_name, checkout)

    if not os.path.isfile(config):
        logger.error(f"Config file {config} not found.")
        if repo:
            logger.error(f"Did you forget to run 'init' to fetch the repo")
        exit(1)

    # Read yaml

    ssf_config = ConfigGenerator(config, yaml=True).load(api=args.api, args=args)
    args = expand_args_from_dict(args, ssf_config)
    ssf_config.args = args

    logger.debug(ssf_config)

    # Check versioning of the yaml
    if MINIMUM_SUPPORTED_VERSION and version.parse(
        ssf_config.ssf_version
    ) < version.parse(MINIMUM_SUPPORTED_VERSION):
        msg = f"ssf_version {ssf_config.ssf_version} is below minimum supported version {MINIMUM_SUPPORTED_VERSION}"
        logger.error(msg)
        raise ValueError(msg)
    if MAXIMUM_SUPPORTED_VERSION and version.parse(
        ssf_config.ssf_version
    ) > version.parse(MAXIMUM_SUPPORTED_VERSION):
        msg = f"ssf_version {ssf_config.ssf_version} is above maximum supported version {MAXIMUM_SUPPORTED_VERSION}"
        logger.error(msg)
        raise ValueError(msg)

    command_config = OrderedDict()
    command_config["init"] = ssf_init
    command_config["build"] = ssf_build
    command_config["run"] = ssf_run
    command_config["package"] = ssf_package
    command_config["test"] = ssf_test
    command_config["publish"] = ssf_publish
    command_config["deploy"] = ssf_deploy

    for cmd_name in command_config:
        if cmd_name in commands:
            if not ipu_count_ok(ssf_config, cmd_name):
                return RESULT_SKIPPED
            ret = command_config[cmd_name](ssf_config)
            if ret != RESULT_OK:
                return ret
            commands = list(filter((cmd_name).__ne__, commands))

    if len(commands):
        logger.error(f"Unknown commands ignored: {commands}")

    return RESULT_OK


def cli():
    result = run(sys.argv[1:])

    logger = logging.getLogger()
    if result == RESULT_OK:
        logger.info(f"Exit with {result} [RESULT_OK]")
    elif result == RESULT_SKIPPED:
        logger.warning(f"Exit with {result} [RESULT_SKIPPED]")
    else:
        logger.error(f"Exit with {result} [ERROR]")

    return result


if __name__ == "__main__":
    exit(cli())
