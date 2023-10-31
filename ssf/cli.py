# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import argparse
import logging
import os
import sys
from packaging import version
from prometheus_client import Histogram
from ssf.common_runtime.common import PROMETHEUS_ENDPOINT, PROMETHEUS_BUCKETS
from typing import Tuple

sys.path.insert(len(sys.path), os.path.abspath(__file__))

from ssf.init import init as ssf_init
from ssf.build import build as ssf_build
from ssf.run import run as ssf_run
from ssf.package import package as ssf_package
from ssf.test import test as ssf_test
from ssf.publish import publish as ssf_publish
from ssf.deploy import deploy as ssf_deploy

from ssf.utils import expand_str, ipu_count_ok, get_supported_apis, API_FASTAPI
from ssf.logger import init_global_logging, set_default_logging_levels, reset_log
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
from ssf.repo import paperspace_load_model as load_model
from ssf.ssh import add_ssh_key
from ssf.config import SSFConfig
from ssf.load_config import ConfigGenerator
from ssf.results import *

DEFAULT_CONFIG = "ssf_config.yaml"
REPO_ROOT = ".repo"
GRADIENT_MODELS_ROOT = ".gradient-model"

# Ordered list of known commands.
SSF_COMMANDS = ["init", "build", "run", "package", "test", "publish", "deploy"]


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
    # - Or -
    #
    # ** From Paperspace model storage **
    #
    # gradient-model:<model-id>|<filename(relative to archive root)>
    #
    # e.g:
    # gradient-model:a23erwfwrerj|ssf_config.yaml
    # .model.zip
    #           |___ ssf_config.yaml
    #           |___ others/
    #   repo: gradient-model
    #   repo_dir: a23erwfwrerj
    #   repo_name: None
    #   config: .gradient-model/ssf_config.yaml
    #   config_file: ssf_config.yaml
    #   checkout: None
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

        if "gradient-model:" in repo:
            repo, repo_dir = repo.split(":")
            config = os.path.join(GRADIENT_MODELS_ROOT, config_file)
        else:
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
    reset_log()

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
    fastapi_op = parser.add_argument_group("# FastAPI API options")
    grpc_op = parser.add_argument_group("# gRPC API options")

    # User can specify which API to generate.
    # Currently this is only REST with FastAPI.
    general_opt.add_argument(
        "-a",
        "--api",
        type=str,
        default=API_FASTAPI,
        choices=get_supported_apis(),
        help="Which API to generate",
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

    # User can override SSF config values.
    general_opt.add_argument(
        "--modify-config",
        type=str,
        default=None,
        help="Add new SSF config fields, or override existing SSF config fields.\n"
        "Values will be set as string literal if the field is new, or must otherwise evaluate to the correct type for an existing field.\n"
        'Syntax:  "<field>=<value>;<field>=<value>;...;". Use "field[<idx>]=...." for list entries.\n'
        'Example: "application.trace=False;endpoints[0].id=my_modified_endpoint"\n',
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

    # User can select replication (of FastAPI server).
    fastapi_op.add_argument(
        "-rs",
        "--fastapi-replicate-server",
        type=int,
        default=1,
        help="Number of server instances",
    )

    # User can define maximal number of connections to gRPC server
    grpc_op.add_argument(
        "--grpc-max-connections",
        type=int,
        default=10,
        help="Maximal number of simultaneous connections to gRPC server.",
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
        help="Set threshold value in seconds for request duration.\n"
        "If exceeded the watchdog will restart the application instance.\n"
        "Value set to 0 (default) disables the request duration watchdog.",
    )

    run_opt.add_argument(
        "--watchdog-request-average",
        type=int,
        default=3,
        help="Set number of last requests included in calculating average watchdog request duration.",
    )

    run_opt.add_argument(
        "--watchdog-ready-period",
        type=int,
        default=5,
        help="Set the time period without a request after which the application instance's watchdog callback function\n"
        "will be polled to check that the application is still ready to receive the next request when it arrives.\n"
        "If the callback function does not return RESULT_OK then the application instance will be restarted.\n"
        "Value set to 0 disables the ready watchdog.",
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

    run_opt.add_argument(
        "--stop-on-error",
        action="store_true",
        help="By default, an application will continue to be served even if in an irrecoverable error state.\n"
        "The health probes (`health/live`, `health/ready`) can be used to detect this occurence.\n"
        "Set this option if you prefer the application to stop and exit immediately on error.",
    )

    run_opt.add_argument(
        "--prometheus-disabled",
        action="store_true",
        help="Disable Prometheus client along with SSF server runtime metrics.",
    )

    run_opt.add_argument(
        "--prometheus-buckets",
        type=float,
        nargs="+",
        default=PROMETHEUS_BUCKETS,
        help="Prometheus buckets to be used with latency and duration metrics.",
    )

    run_opt.add_argument(
        "--prometheus-endpoint",
        type=str,
        default=PROMETHEUS_ENDPOINT,
        help="Address of Prometheus metrics endpoint.",
    )

    run_opt.add_argument(
        "--prometheus-port",
        type=str,
        default="",
        help="If prometheus-port is is not specified then the Prometheus metrics will share an HTTP server with the service.\n"
        "If prometheus-port is specified then two separate HTTP servers will run - one for Prometheus metrics and one for the service.",
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
            "Paperspace",
            "Gcore",
        ],
        help="The target platform for deployment.\n"
        "Gcore deployments start or update a deployment at the specified remote target address using a simple bash boot script and ssh.\n"
        "Paperspace deployments create a deployment spec and use the Gradient API to run or update it.",
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
        "--deploy-custom-args",
        type=str,
        default=None,
        help="Add additional custom SSF arguments to the deployment SSF CLI invocation.\n"
        "The specified argument string will be appended to the default SSF_OPTIONS environment variable that is constructed to pass SSF arguments to the remote target image.",
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

    deploy_opt.add_argument(
        "--deploy-paperspace-registry",
        type=str,
        default="Graphcore Cloud Solutions Dev R-O",
        help="Paperspace: The containerRegistry entry when auto generating the deployment specification for deployment.",
    )

    deploy_opt.add_argument(
        "--deploy-paperspace-project-id",
        type=str,
        default=None,
        help="Paperspace: The deployment platform project ID.",
    )

    deploy_opt.add_argument(
        "--deploy-paperspace-cluster-id",
        type=str,
        default="clehbtvty",
        help="Paperspace: The deployment platform cluster ID.",
    )

    deploy_opt.add_argument(
        "--deploy-paperspace-api-key",
        type=str,
        default=None,
        help="Paperspace: Name of the environment variable where your token is stored (do not write your token directly here).",
    )

    deploy_opt.add_argument(
        "--deploy-paperspace-replicas",
        type=int,
        default=1,
        help="Paperspace: Number of deployment instances (containers) to start.",
    )

    deploy_opt.add_argument(
        "--deploy-paperspace-spec-file",
        type=str,
        default=None,
        help="Paperspace: The deployment specification will be generated automatically if one is required for the platform.\n"
        "It can be overridden with this argument.",
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

    if len(cli_args) == 0:
        parser.print_help()
        return RESULT_OK

    # Extract known command args from the cli_args list before parsing with the argparser.
    # This allows for more robust support of a mix of unknown args and commands.
    # For example, this would otherwise fail: "build --unknown run X init Y"
    # We must guarantee that the SSF_COMMANDS remain unique strings.
    stripped_commands = []
    stripped_cli_args = []
    for a in cli_args:
        stripped_commands.append(a) if a in SSF_COMMANDS else stripped_cli_args.append(
            a
        )
    try:
        args, unknown_args = parser.parse_known_intermixed_args(stripped_cli_args)
    except SystemExit as e:
        if "--help" in cli_args or "-h" in cli_args:
            return RESULT_OK
        raise SSFExceptionArgumentsError() from e
    args.commands += stripped_commands

    # Helper to expand args (replace symbolic references with values from ssf config).
    # To support, e.g,
    #   --package-tag "my-release-repo:{{application.id}}-{{application.version}}-latest"
    # NOTE:
    #  The modify_config arg is skipped, since this argument contains lines/mods for the ssf_config
    #  that are applied before expanding args; this may include refs to other ssf_config fields
    #  that shouldn't really be expanded here.
    def expand_args_from_dict(args: argparse.Namespace, ssf_config: dict):
        a = vars(args)
        for k, v in a.items():
            if isinstance(v, str):
                if k != "modify_config":
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
            raise SSFExceptionArgumentsError(msg)

    if args.deploy_name and " " in args.deploy_name:
        raise SSFExceptionArgumentsError("--deploy-name should not contain any space")
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

            ssf_config = ConfigGenerator(
                ssf_config_dict, yaml=False, modify_config=args.modify_config
            ).load(self_package=True, args=args)
            args = expand_args_from_dict(args, ssf_config.config_dict)
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
        if "gradient-model" in repo:
            logger.info(f"> Pulling model from Gradient")
            model_id, repo_path = repo_dir, GRADIENT_MODELS_ROOT
            load_model(repo_path, model_id, args)
        else:
            logger.info(f"> Cloning repo")
            repo_clone(repo, repo_dir, repo_name, checkout)

    if not os.path.isfile(config):
        if repo:
            logger.error(f"Did you forget to run 'init' to fetch the repo")
        raise SSFExceptionArgumentsError(f"Missing config file {config}")

    # Read yaml

    ssf_config = ConfigGenerator(
        config, yaml=True, modify_config=args.modify_config
    ).load(api=args.api, args=args)
    args = expand_args_from_dict(args, ssf_config.config_dict)

    ssf_config.args = args
    ssf_config.unknown_args = unknown_args
    if ssf_config.unknown_args:
        logger.warning(f"Ignoring unknown arguments {ssf_config.unknown_args}")

    logger.debug(ssf_config)

    # Check versioning of the yaml
    if MINIMUM_SUPPORTED_VERSION and version.parse(
        ssf_config.ssf_version
    ) < version.parse(MINIMUM_SUPPORTED_VERSION):
        msg = f"ssf_version {ssf_config.ssf_version} is below minimum supported version {MINIMUM_SUPPORTED_VERSION}"
        raise SSFExceptionArgumentsError(msg)
    if MAXIMUM_SUPPORTED_VERSION and version.parse(
        ssf_config.ssf_version
    ) > version.parse(MAXIMUM_SUPPORTED_VERSION):
        msg = f"ssf_version {ssf_config.ssf_version} is above maximum supported version {MAXIMUM_SUPPORTED_VERSION}"
        raise SSFExceptionArgumentsError(msg)

    # Extend system path with config, app module and user-specified directories.
    # NOTE: The last added takes precedence so order is important here.
    def add_sys_path(path: str):
        if path not in sys.path:
            logger.info(f"Adding syspath {path}")
            sys.path.insert(0, path)

    add_sys_path(ssf_config.application.dir)
    add_sys_path(ssf_config.application.file_dir)
    if ssf_config.application.syspaths:
        for p in reversed(ssf_config.application.syspaths):
            p = os.path.abspath(os.path.join(ssf_config.application.dir, p))
            add_sys_path(p)

    # Iterate known commands in sequence.
    for cmd_name in SSF_COMMANDS:
        if cmd_name in commands:
            if not ipu_count_ok(ssf_config, cmd_name):
                raise SSFExceptionUnmetRequirement(
                    f"IPUs count does not match application requirements."
                )
            ret = globals()[f"ssf_{cmd_name}"](ssf_config)
            if ret != RESULT_OK:
                return ret
            commands = list(filter((cmd_name).__ne__, commands))

    if len(commands):
        logger.warning(f"Ignoring unknown SSF commands {commands}")
    return RESULT_OK


def cli():
    logger = logging.getLogger()
    result = RESULT_INTERNAL_ERROR
    try:
        result = run(sys.argv[1:])
    except SSFException as e:
        result = e.result_code
        if e.log_with_level:
            logger.log(e.log_with_level, e)
        else:
            logger.exception(e)
    except SystemExit as e:
        if e.code:
            logger.exception(e)
            result = RESULT_INTERNAL_ERROR
        else:
            result = RESULT_OK
    except Exception as e:
        result = RESULT_INTERNAL_ERROR
        logger.exception(e)
    finally:
        logger.info(f"Exit with {result}")
        return result


if __name__ == "__main__":
    exit(cli())
