# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os

from typing import List, Dict, Optional, Union
from yaml import safe_load as yaml_safe_load
from argparse import Namespace

from ssf.application_interface.config import (
    SSFConfig,
    ApplicationDescription,
    EndpointDescription,
    PackageDescription,
    EndpointParam,
)
from ssf.application_interface.results import SSFExceptionApplicationConfigError

from ssf.version import PACKAGE_DEFAULT_BASEIMAGE
from ssf.utils import get_endpoints_gen_module_path, set_dict

logger = logging.getLogger("ssf")


def validate_id(id, debug_name):
    if " " in id:
        raise SSFExceptionApplicationConfigError(
            f"Invalid config file: {debug_name} should not contain spaces"
        )
    return


class ConfigGenerator:
    """
    ConfigGenerator:
    Loads and expands YAML file to dictionary, or initialises dictionary with user config.

    Args:
    config: [str, Dict] Path to SSF config .yaml file if loading from file, else an internally loaded dictionary format.
    yaml:   [bool] If true, will load config .yaml file from `config` arg, otherwise will interpret config arg as Dict.

    Returns:
    None
    """

    def __init__(
        self, config: Union[str, Dict], yaml: bool = True, modify_config: str = None
    ) -> None:

        if yaml:
            try:
                assert isinstance(config, str)
            except AssertionError as e:
                raise SSFExceptionApplicationConfigError(
                    f"`yaml` set to True when loading config, expected `config` argument to be [str] path to YAML file. Got {type(config)}."
                ) from e

            try:
                ssf_config = yaml_safe_load(open(config))
            except Exception as e:
                raise SSFExceptionApplicationConfigError(
                    f"Failure loading {config}."
                ) from e

            config_file = config
        else:
            try:
                assert isinstance(config, Dict)
            except AssertionError as e:
                raise SSFExceptionApplicationConfigError(
                    f"`yaml` set to False when loading config, expected `config` argument to be [Dict] config dict. Got {type(config)}."
                ) from e

            ssf_config = config
            config_file = None

        if modify_config is not None:
            mclist = modify_config.split(";")
            failures = 0
            for mc in mclist:
                logger.info(f"Modify config: {mc}")
                field_value = mc.split("=")
                if len(field_value) != 2:
                    failures += 1
                    logger.error(
                        f"Modify config failure with '{mc}', requires '<field>=<value>'"
                    )
                elif not set_dict(ssf_config, field_value[0], field_value[1]):
                    failures += 1
                    logger.error(f"Config field can not be set with `{mc}`")
            if failures > 0:
                raise SSFExceptionApplicationConfigError(
                    f"Failed to modify config with `{mclist}`"
                )

        self.config_dict = ssf_config
        self.__expand_dict(self.config_dict)
        self.config_file = config_file

    def load(
        self,
        api: str = None,
        self_package: bool = False,
        args: Namespace = None,
    ) -> SSFConfig:

        """
        ConfigGenerator.load():

        Creates fully loaded SSFConfig class with all required fields in a dataclass object and initialises any defaults.

        api:    [str] Which API to use - default to FastAPI.
        args:   [argparse.Namespace] Expects parsed CLI args in argparse.Namespace format.
        self_package_or_publish: [bool] If true, will assume self-packaging behaviour. Will not check for endpoint specific information in config.

        Returns: SSFConfig class containing all required configuration.
        """

        # Create base config
        config = SSFConfig()

        config.ssf_version = self.__setter("ssf_version", config.ssf_version)
        config.config_file = self.config_file
        config.config_dict = self.config_dict
        config.args = args
        config.api = api

        config.application = self.init_application_config(
            self.config_file, self_package, args
        )

        if not self_package:
            config.endpoints = self.init_endpoints_config(config.application, api)

        return config

    def init_application_config(
        self,
        config_file: str,
        self_package: bool,
        args: Namespace,
    ) -> ApplicationDescription:

        # Set application level configs from dict - first initialise with defaults
        self.__setter("application", assert_required=True)
        application = ApplicationDescription()

        # Level moved to config["application"]
        level = ["application"]

        application.id = self.__setter("id", application.id, level)
        validate_id(application.id, "application.id")
        application.name = self.__setter("name", application.name, level)
        application.version = self.__setter("version", application.version, level)

        application.license_name = self.__setter(
            "license_name", application.license_name, level
        )
        application.license_url = self.__setter(
            "license_url", application.license_url, level
        )
        application.terms_of_service = self.__setter(
            "terms_of_service", application.terms_of_service, level
        )

        application.startup_timeout = self.__setter(
            "startup_timeout", application.startup_timeout, level
        )

        application.package = self.init_package_config(application, args)

        # ... more application fields that are expected for self packaging/publishing can be assigned here (e.g. fields at the level of config["application"])

        if not self_package:
            # Set rest of application level fields not required when self packaging/publishing

            application.description = self.__setter(
                "desc", application.description, level
            )
            application.artifacts = self.__setter(
                "artifacts", application.artifacts, level
            )
            application.dependencies = self.__setter(
                "dependencies", application.dependencies, level
            )
            application.trace = self.__setter("trace", application.trace, level)
            application.ipus = self.__setter("ipus", application.ipus, level)
            application.max_batch_size = self.__setter(
                "max_batch_size", application.max_batch_size, level
            )
            if args:
                application.total_ipus = (
                    application.ipus
                    * args.fastapi_replicate_server
                    * args.replicate_application
                )
            application.syspaths = self.__setter(
                "syspaths", application.syspaths, level
            )

            # Assume application module (file) as required if not self packaging/publishing
            application.file = self.__setter(
                "module", level=level, assert_required=True
            )

            # Handle app directory setting
            if config_file:
                application.dir = os.path.dirname(os.path.abspath(config_file))
                relative_application_file = os.path.join(
                    application.dir, application.file
                )
                if os.path.isfile(relative_application_file):
                    application.file = relative_application_file
                else:
                    logger.warning(
                        "Application file not found relative to config - using specified module path."
                    )
                application.file_dir = os.path.dirname(
                    os.path.abspath(application.file)
                )
                application.venv_dir = os.path.join(
                    os.getcwd(), f"ssf-{application.id}-venv"
                )

            # Handle dependency types
            for i in application.dependencies:
                if i not in ["python", "poplar", "poplar_wheels", "poplar_location"]:
                    logger.warning(
                        "Only python, poplar, poplar_wheels and poplar_location dependencies are supported. Other packages will not be installed."
                    )

            if application.dependencies.get("poplar") is None:
                if application.dependencies.get("poplar_wheels") is not None:
                    raise SSFExceptionApplicationConfigError(
                        f"application.dependencies.poplar_wheels requires application.dependencies.poplar to be set."
                    )
                if application.dependencies.get("poplar_location") is not None:
                    raise SSFExceptionApplicationConfigError(
                        f"application.dependencies.poplar_location requires application.dependencies.poplar to be set."
                    )

            # Keep interface as None - to be set later
            application.interface = None

            # ... more application fields that are not expected for self packaging/publishing can be assigned here (e.g. fields at the level of config["application"])

        else:
            logger.info("Self packaging/publishing SSF with reduced config.")

        return application

    def init_package_config(self, application: ApplicationDescription, args: Namespace):
        level = ["application"]

        package_dict = self.__setter("package", None, level)
        package = PackageDescription()

        default_package_name = f"{application.id}.{application.version}.tar.gz"
        default_package_tag = f"{application.id}:{application.version}"

        if package_dict is not None:
            # Level moved to config["application"]["package"]
            level = ["application", "package"]

            package.name = self.__setter("name", default_package_name, level)
            package.tag = self.__setter("tag", default_package_tag, level)
        else:
            package.name = default_package_name
            package.tag = default_package_tag

        package.docker = self.__setter("docker", None, level)

        # Priority is given to args.package_baseimage - otherwise tries to set from config - otherwise default
        if args and args.package_baseimage is not None:
            package.base_image = args.package_baseimage
        else:
            package.base_image = PACKAGE_DEFAULT_BASEIMAGE

        if package.docker:
            package.base_image = self.__setter(
                "baseimage", package.base_image, level + ["docker"]
            )

            package.docker_run = self.__setter("run", "", level + ["docker"])

        package.inclusions = self.__setter("inclusions", [], level)
        package.exclusions = self.__setter("exclusions", [], level)

        # ... more package fields can be assigned here - (e.g. fields inside config["application"]["package"])

        return package

    def init_endpoints_config(
        self,
        application: ApplicationDescription,
        api: str = None,
    ) -> EndpointDescription:

        self.__setter("endpoints", assert_required=True)
        endpoints = [EndpointDescription() for _ in self.config_dict["endpoints"]]

        for idx, endpoint in enumerate(endpoints):
            # Level moved to config["endpoints"][idx]
            level = ["endpoints", idx]
            endpoint.index = idx
            endpoint.id = self.__setter("id", f"{endpoint.id}_{idx}", level)
            validate_id(endpoint.id, "endpoint.id")
            endpoint.version = self.__setter("version", endpoint.version, level)
            endpoint.description = self.__setter("desc", endpoint.description, level)
            endpoint.custom = self.__setter("custom", endpoint.custom, level)

            if endpoint.custom:
                endpoint.file = os.path.join(application.dir, endpoint.custom)
                endpoint.generate = False
            else:
                endpoint.file = os.path.join(
                    os.getcwd(), f"ssf-{application.id}-endpoint-{idx}-{api}.py"
                )
                endpoint.generate = os.path.exists(get_endpoints_gen_module_path(api))

            # Currently the default API is FastAPI, behaviours for different frameworks can be mapped in future
            # If no option is set, the default is None - as this behaviour dynamically changes when endpoint is generated.
            endpoint.http_param_format = self.__setter(
                "http_param_format", endpoint.http_param_format, level
            )

            # ... more endpoint fields can be assigned here (e.g. fields inside config["endpoint"])

            endpoint.inputs = self.init_endpoint_params(endpoint, "inputs")
            endpoint.outputs = self.init_endpoint_params(endpoint, "outputs")

        return endpoints

    def init_endpoint_params(
        self, endpoint: EndpointDescription, param_field: str = "inputs"
    ):
        idx = endpoint.index

        if param_field in self.config_dict["endpoints"][idx]:
            params = [
                EndpointParam() for _ in self.config_dict["endpoints"][idx][param_field]
            ]

            for iidx, endpoint_param in enumerate(params):
                # Level moved to config["endpoints"][idx][param_field][iidx]
                i_level = ["endpoints", idx, param_field, iidx]

                endpoint_param.id = self.__setter("id", f"input_{iidx}", i_level)
                validate_id(endpoint_param.id, "endpoint_param.id")
                endpoint_param.dtype = self.__setter(
                    "type", None, i_level, assert_required=True
                )
                endpoint_param.description = self.__setter(
                    "desc", f"Endpoint {param_field} {iidx}", i_level
                )
                endpoint_param.example = self.__setter("example", None, i_level)

                # ... more endpoint parameter fields can be assigned here (e.g. fields inside config["endpoints"][idx]["input"/"output"][idx])

            return params

        else:
            logger.warning(f"No {param_field} specified for endpoint: {idx}.")

        return None

    def __setter(
        self,
        key: str,
        var=None,
        level: List[Optional[str]] = None,
        assert_required=False,
    ):
        d = self.config_dict

        if level:
            for i in level:
                d = d[i]

        if assert_required:
            try:
                assert key in d
            except AssertionError as e:
                raise SSFExceptionApplicationConfigError(
                    f"Required field '{key}' not found in config YAML file."
                ) from e

        if key not in d:
            logger.info(
                f"{'.'.join([str(k) for k in (level + [key])])} not specified. Defaulting to '{var}'"
            )
            return var
        else:
            return d[key]

    def __expand_dict(self, d):
        from ssf.utils import expand_str

        for key, entry in d.items():
            if isinstance(entry, str):
                d[key] = expand_str(entry, self.config_dict)
            elif isinstance(entry, dict):
                self.__expand_dict(entry)
            elif isinstance(entry, list):
                for idx in range(len(entry)):
                    if isinstance(entry[idx], dict):
                        self.__expand_dict(entry[idx])
                    elif isinstance(entry[idx], str):
                        entry[idx] = expand_str(entry[idx], self.config_dict)
