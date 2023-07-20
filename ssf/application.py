# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Union, Tuple

import logging
import os

from ssf.utils import install_python_requirements
from ssf.utils import install_python_packages
from ssf.utils import load_module, temporary_cwd

from ssf.config import SSFConfig


class SSFApplicationInterface(ABC):
    @abstractmethod
    def build(self) -> int:
        """
        Build required dependencies.
        This could be building custom-ops, binary executables, model-preprocessing
        Consider running of the model to capture a popef file as an optimisation.
        This is called when `ssf build` is issued.

        Returns:
                0 if successful.
        """

    @abstractmethod
    def startup(self) -> int:
        """
        One-time startup for the application instance.
        Consider priming the application instance by issuing a dummy request.
        This is called during `ssf run` before requests are started.

        Returns:
                0 if successful.
        """

    @abstractmethod
    def request(
        self, params: Union[dict, list], meta: Union[dict, list]
    ) -> Union[dict, list]:
        """
        Request for inference.
        This is called by the dispatcher for each queued request while `ssf run` is running.

        Parameters:
                params (dict | list): Input parameters as a dictionary; Dictionary fields must match inputs declared in the SSF config.
                meta (dict | list): Metadata fields such as endpoint_id, endpoint_version and endpoint_index to support multiple or versioned endpoints.
        Returns:
                Output parameters as a dictionary or list of dictionaries; Dictionary fields must match outputs declared in the SSF config.
        Note:
                When max_batch_size in ssf config is greater than 1 then input parameters will be list of dictionaries and respectively return values must be list of dictionaries.
        """

    @abstractmethod
    def shutdown(self) -> int:
        """
        One-time shutdown for the application instance.
        This is called during `ssf run` when requests are stopped.

        Returns:
                0 if successful.
        """

    def is_healthy(self) -> bool:
        """
        Called periodically shall report application specific unrecoverable failures.
        Returning false will cause the server to restart the application replica.
        When no specific errors can be detected or they are handled internally default implementation can be used.

        Returns:
                True during correct runtime, False otherwise
        """
        return True


def install_application_dependencies(ssf_config: SSFConfig):
    python_dependencies = ssf_config.application.dependencies["python"]

    if python_dependencies is None:
        return

    # Support single 'requirements.txt' or comma-separated list 'Pillow>=9.4.0,numpy==1.23.1'
    if ".txt" in python_dependencies:
        requirements_file = os.path.join(
            ssf_config.application.dir, python_dependencies
        )
        if install_python_requirements(requirements_file):
            raise ValueError(
                f"failed to install application dependencies with {requirements_file}"
            )
    else:
        if install_python_packages(python_dependencies):
            raise ValueError(
                f"failed to install application dependencies with {python_dependencies}"
            )


def get_application(ssf_config: SSFConfig):
    # NOTE:
    # This creates just one instance for the current process.
    # It is cached and returned on any subsequent call to get_application().
    # When using replication, it is assumed that each replica (e.g. dispatcher) will
    # run in its own process space and therefore create its own application instance.
    logger = logging.getLogger("ssf")

    if ssf_config.application.interface:
        logger.info(f"Application interface already created")
    else:
        logger.info(f"Creating application interface")
        logger.info(f"Checking application dependencies")
        install_application_dependencies(ssf_config)

        application_id = ssf_config.application.id
        application_file = ssf_config.application.file
        module_id = ssf_config.application.id

        logger.info(
            f"Loading {application_id} application from {application_file} with module id {module_id}"
        )
        application_module = load_module(application_file, module_id)
        logger.info(application_module)

        # Where the user's application module sources are.
        app_file_dir = ssf_config.application.file_dir

        # Run create_ssf_application_instance from application directory.
        with temporary_cwd(app_file_dir):
            # Create and return ssf application instance.
            ssf_config.application.interface = (
                application_module.create_ssf_application_instance()
            )

    return ssf_config.application.interface


def clear_application(ssf_config: SSFConfig):
    # NOTE:
    # An application instance may import modules and set up globals in this process,
    # this will not reverse it.
    logger = logging.getLogger("ssf")
    if ssf_config.application.interface:
        ssf_config.application.interface = None
    else:
        logger.warning(f"clear_application: No application found in ssf_config.")


class SSFApplicationTestInterface(ABC):
    @abstractmethod
    def begin(self, session, ipaddr: str) -> int:
        """
        Begin application testing.
                session: The Python requests library session (credentials are initialised before calling into application tests).
                ipaddr (str): IP address including port (e.g. "http://0.0.0.0:8100")
        Returns:
                0 if successful.
        """

    @abstractmethod
    def subtest(self, session, ipaddr: str, index: int) -> Tuple[bool, str, bool]:
        """
        Issue test.

        Parameters:
                session: The Python requests library session (credentials are initialised before calling into application tests).
                ipaddr (str): IP address including port (e.g. "http://0.0.0.0:8100")
                index (int): Subtest index, starting at zero after 'begin' and incrementing with each call to subtest.
        Returns:
                tuple ((bool, str, bool)): True if test passed, a human-readable description of the result (for logging), True to continue running tests.
        """

    @abstractmethod
    def end(self, session, ipaddr: str) -> int:
        """
        End application testing.
                session: The Python requests library session (credentials are initialised before calling into application tests).
                ipaddr (str): IP address including port (e.g. "http://0.0.0.0:8100")
        Returns:
                0 if successful.
        """


def get_application_test(ssf_config: SSFConfig):
    # NOTE:
    # This creates and returns an instance of the application test if it exists, or None.
    # It is NOT cached.
    logger = logging.getLogger("ssf")
    logger.info(f"Creating application test")
    logger.info(f"Checking application dependencies")
    install_application_dependencies(ssf_config)

    application_id = ssf_config.application.id
    application_file = ssf_config.application.file
    module_id = ssf_config.application.id
    logger.info(
        f"Loading {application_id} application test from {application_file} with module id {module_id}"
    )
    application_module = load_module(application_file, module_id)
    logger.info(application_module)

    # Create and return ssf application test instance.
    try:
        # Where the user's application sources are.
        app_file_dir = ssf_config.application.file_dir
        # Run create_ssf_application_test_instance from application module file directory.
        with temporary_cwd(app_file_dir):
            # ssf_config passed as copy to isolate application config
            return application_module.create_ssf_application_test_instance(
                deepcopy(ssf_config)
            )
    except:
        logger.debug(
            f"Could not create {application_id} application test from {application_file} with module id {module_id}"
        )
    return None
