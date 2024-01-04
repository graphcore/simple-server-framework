# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import sys
import shutil

from ssf.application_interface.results import *
from ssf.application_interface.config import SSFConfig
from ssf.utils import install_python_requirements
from ssf.utils import install_python_packages
from ssf.utils import logged_subprocess
from ssf.utils import get_poplar_requirement
from ssf.utils import get_python_requirements
from ssf.sdk_utils import get_poplar_sdk, get_poplar_wheels

logger = logging.getLogger("ssf")


def create_app_venv(ssf_config: SSFConfig):
    # Only check for pre-existence.
    # The user must use 'init' to reset and force rebuild if that is required.
    app_env = ssf_config.application.venv_dir
    if os.path.isdir(app_env):
        logger.info(f"> Using existing application venv {app_env}")
    else:
        logger.info(f"> Creating application venv {app_env}")
        logged_subprocess("venv", [sys.executable, "-m", "venv", app_env])
        install_application_dependencies(ssf_config)


def destroy_app_venv(ssf_config: SSFConfig):
    app_env = ssf_config.application.venv_dir
    if os.path.isdir(app_env):
        logger.info(f"> Cleaning application venv {app_env}")
        shutil.rmtree(app_env)


def install_application_dependencies(ssf_config: SSFConfig):
    if ssf_config.application.dependencies is None:
        return

    # app venv's Python
    py_executable = os.path.join(ssf_config.application.venv_dir, "bin/python")

    # Install pip dependencies
    if (
        "python" in ssf_config.application.dependencies
        and ssf_config.application.dependencies.get("python") is not None
    ):

        deps_requirement_files, deps_packages = get_python_requirements(ssf_config)

        for requirements_file in deps_requirement_files:
            if install_python_requirements(requirements_file, py_executable):
                raise SSFExceptionInstallationError(
                    f"Failed to install application dependencies with {requirements_file}"
                )
        if len(deps_packages) > 0:
            if install_python_packages(",".join(deps_packages), py_executable):
                raise SSFExceptionInstallationError(
                    f"Failed to install application dependencies with {deps_packages}"
                )

    # Install Poplar dependencies in app venv
    if get_poplar_requirement(ssf_config) is not None:
        sdk_path = get_poplar_sdk(ssf_config)
        poplar_wheels = ssf_config.application.dependencies.get("poplar_wheels", False)
        if poplar_wheels:
            wheels, missing = get_poplar_wheels(poplar_wheels, sdk_path)
            if len(missing):
                raise SSFExceptionInstallationError(
                    f"Could not find .whl for {','.join(missing)} in {sdk_path}"
                )
            for wheel in wheels:
                if install_python_packages(wheel, py_executable):
                    raise SSFExceptionInstallationError(
                        f"Failed to install sdk_package {wheel}"
                    )
