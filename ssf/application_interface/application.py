# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# NOTE:
# Do not import external packages in application_interface modules
# to avoid introducing additional dependencies for the application.
# Only import SSF modules that are also in application_interface.

from abc import abstractmethod, ABCMeta
from copy import deepcopy
import inspect
from functools import wraps
import logging
import os
import sys
from types import FunctionType
import types
from typing import Union, Tuple

from ssf.application_interface.results import *
from ssf.application_interface.config import SSFConfig
from ssf.application_interface.utils import load_module, temporary_cwd


def exception_wrapper(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except SSFException as e:
            raise e
        except Exception as e:
            raise SSFExceptionApplicationError(
                f"Application `{method.__name__}` api call failed."
            ) from e

    return wrapped


class ExceptionInterceptMetaClass(type):
    def __new__(meta, classname, bases, classDict):
        newClassDict = {}
        for attributeName, attribute in classDict.items():
            if isinstance(attribute, FunctionType):
                # replace it with a wrapped version
                attribute = exception_wrapper(attribute)
            newClassDict[attributeName] = attribute
        return type.__new__(meta, classname, bases, newClassDict)


class ApplicationMeta(ABCMeta, ExceptionInterceptMetaClass):
    pass


class SSFApplicationInterface(metaclass=ApplicationMeta):
    @abstractmethod
    def build(self) -> int:
        """
        Build required dependencies.
        This could be building custom-ops, binary executables, or model-preprocessing.
        Consider running the model to capture a popEF file as an optimisation.
        This is called when `ssf build` is issued.

        Returns:
                0 (RESULT_OK) if successful.
        """

    @abstractmethod
    def startup(self) -> int:
        """
        One-time startup for the application instance.
        Consider priming the application instance by issuing a dummy request.
        This is called during `ssf run` before requests are started.

        Returns:
                0 (RESULT_OK) if successful.
        """

    @abstractmethod
    def request(
        self, params: Union[dict, list], meta: Union[dict, list]
    ) -> Union[dict, list]:
        """
        Request for inference.
        This is called by the dispatcher for each queued request while `ssf run` is running.

        Parameters:
                params (dict | list): Input parameters as a dictionary; dictionary fields must match inputs declared in the SSF config.
                meta (dict | list): Metadata fields such as endpoint_id, endpoint_version and endpoint_index to support multiple or versioned endpoints.
        Returns:
                Output parameters as a dictionary or list of dictionaries; dictionary fields must match outputs declared in the SSF config.
        Note:
                When max_batch_size in ssf config is greater than 1 then input parameters will be list of dictionaries and respectively return values must be list of dictionaries.
        """

    @abstractmethod
    def shutdown(self) -> int:
        """
        One-time shutdown for the application instance.
        This is called during `ssf run` when requests are stopped.

        Returns:
                0 (RESULT_OK) if successful.
        """

    def watchdog(self) -> int:
        """
        Called after a period of request inactivity to check the application instance is still ready to receive requests.
        If the application instance has an unrecoverable failure then its watchdog can return failure which will cause the server to restart the application instance.
        If failures can not be detected, or they are handled internally, the default implementation can be used.

        Returns:
               0 (RESULT_OK) if successful.
        """
        return RESULT_OK


class SSFApplicationTestInterface(metaclass=ApplicationMeta):
    @abstractmethod
    def begin(self, session, ipaddr: str) -> int:
        """
        Begin application testing.
                session: The Python requests library session (credentials are initialised before calling into application tests).
                ipaddr (str): IP address including port (for example "http://0.0.0.0:8100").
        Returns:
                0 if successful.
        """

    @abstractmethod
    def subtest(self, session, ipaddr: str, index: int) -> Tuple[bool, str, bool]:
        """
        Issue test.

        Parameters:
                session: The Python requests library session (credentials are initialised before calling into application tests).
                ipaddr (str): IP address including port (for example "http://0.0.0.0:8100").
                index (int): Subtest index, starting at zero after 'begin' and incrementing with each call to subtest.
        Returns:
                tuple ((bool, str, bool)): True if test passed, a human-readable description of the result (for logging), True to continue running tests.
        """

    @abstractmethod
    def end(self, session, ipaddr: str) -> int:
        """
        End application testing.
                session: The Python requests library session (credentials are initialised before calling into application tests).
                ipaddr (str): IP address including port (for example "http://0.0.0.0:8100").
        Returns:
                0 if successful.
        """


def watchdog_from_is_healthy(self) -> int:
    return RESULT_OK if self.is_healthy() else RESULT_APPLICATION_ERROR


def instantiate_application(
    ssf_config: SSFConfig, app_cls: str, factory_fn: str, debug_name: str
):
    # This creates and returns an instance of `app_cls`
    # if it exists or if the user factory method `factory_fn` exists.
    # Returns None if none of the above exists (not catching).
    # (factory_fn takes priority if it exists)

    # The factory may optionally include the ssf_config with this signature:
    #   factory_fn()
    #   factory_fn(ssf_config)
    # The class may optionally include the ssf_config with this signature for the init method:
    #   __init__(self)
    #   __init__(self, ssf_config)

    logger = logging.getLogger("ssf")
    logger.info(f"Creating application " + debug_name)

    application_id = ssf_config.application.id
    application_file = ssf_config.application.file
    module_id = ssf_config.application.id

    logger.info(
        f"Loading {application_id} application {debug_name} from {application_file} with module id {module_id}"
    )
    application_module = load_module(application_file, module_id)
    logger.info(application_module)

    def find_builder():
        for name, obj in inspect.getmembers(application_module):
            if inspect.isfunction(obj) and obj.__name__ == factory_fn:
                return obj
        return False

    error_message = f"Could not create {application_id} application {debug_name} from {application_file} with module id {module_id}"
    builder = find_builder()

    # Make a copy of the ssf_config but with shared context
    def make_ssf_config():
        nonlocal ssf_config
        ssf_config_copy = deepcopy(ssf_config)
        # The SSF config is copied so the user's application can't modify our internal state.
        # We could choose to make some part of the app config modifiable - for example a 'context'.
        # This is tested and can work, but we don't have a real use case, so it is removed for now.
        # ssf_config_copy.context = ssf_config.context
        return ssf_config_copy

    # If the user has defined a factory method
    if builder:
        logger.debug(
            f"Application instantiated by user-defined function`{factory_fn}`."
        )
        # Where the user's application module sources are.
        app_file_dir = ssf_config.application.file_dir
        try:
            # Run application instance from application directory.
            with temporary_cwd(app_file_dir):
                # Create and return ssf application instance from user builder.
                argspec = inspect.getfullargspec(builder)
                logger.debug(f"Application factory argspec {argspec}")
                if len(argspec.args) == 1 and argspec.args[0] == "ssf_config":
                    return builder(ssf_config=make_ssf_config())
                else:
                    return builder()
        except SSFExceptionUnmetRequirement as e:
            raise e
        except Exception as e:
            raise SSFExceptionApplicationModuleError(
                error_message + " " + f" using {factory_fn}."
            ) from e

    # Else, try to find and instantiate the application here
    else:
        logger.debug(f"Function `{factory_fn}` was not defined. Using default builder.")
        # Build a default instance if possible
        application_interface = []
        for name, obj in inspect.getmembers(application_module):
            if inspect.isclass(obj):
                if app_cls in [c.__name__ for c in inspect.getmro(obj) if c != obj]:
                    logger.info(f"Found {obj}, {name}")
                    application_interface.append(obj)

        if len(application_interface) == 1:
            application_interface = application_interface[0]
            try:
                signature = inspect.signature(application_interface.__init__).parameters
                logger.debug(f"Application interface signature {signature}")
                if (
                    len(signature) == 2
                    and "self" in signature
                    and "ssf_config" in signature
                ):
                    return application_interface(ssf_config=make_ssf_config())
                else:
                    return application_interface()
            except SSFExceptionUnmetRequirement as e:
                raise e
            except Exception as e:
                raise SSFExceptionApplicationModuleError(
                    error_message
                    + ". "
                    + f"If {application_interface} needs a non-trivial initialisation "
                    f"you can define `{factory_fn}` in your application file."
                ) from e

        elif len(application_interface) > 1:
            raise SSFExceptionApplicationModuleError(
                error_message
                + ". "
                + f"Only one application {debug_name} should be defined. Found {len(application_interface)}. "
                f"To make it unambiguous, please define the function `{factory_fn}` in your application file."
            )

        logger.debug(f"No application {app_cls} class was found.")

    return None


def check_interface(interface, id, logger=None):
    if hasattr(interface, id) and callable(getattr(interface, id)):
        return True
    if logger is not None:
        logger.error(f"Interface '{id}' missing or not callable")
    return False


def get_application(ssf_config: SSFConfig):
    # NOTE:
    # This creates just one instance for the current process.
    # It is cached and returned on any subsequent call to get_application().
    # When using replication, it is assumed that each replica's dispatcher will
    # run in its own process space and therefore create its own application instance.
    logger = logging.getLogger("ssf")

    if ssf_config.application.interface:
        logger.info(f"Application interface already created")
    else:
        ssf_config.application.interface = instantiate_application(
            ssf_config,
            app_cls="SSFApplicationInterface",
            factory_fn="create_ssf_application_instance",
            debug_name="main interface",
        )

    if ssf_config.application.interface is None:
        raise SSFExceptionApplicationModuleError(
            "Failure creating application instance. "
            "Make sure that you implemented `SSFApplicationInterface` "
            "in your application file"
        )

    if check_interface(ssf_config.application.interface, "is_healthy"):
        logger.warning(
            "Application interface 'is_healthy' has been renamed to 'watchdog'"
        )
        logger.warning("Using application interface 'is_healthy' as 'watchdog'")
        setattr(
            ssf_config.application.interface,
            "watchdog",
            types.MethodType(
                watchdog_from_is_healthy, ssf_config.application.interface
            ),
        )

    OK = True
    OK = check_interface(ssf_config.application.interface, "build", logger) and OK
    OK = check_interface(ssf_config.application.interface, "startup", logger) and OK
    OK = check_interface(ssf_config.application.interface, "request", logger) and OK
    OK = check_interface(ssf_config.application.interface, "shutdown", logger) and OK
    OK = check_interface(ssf_config.application.interface, "watchdog", logger) and OK
    if not OK:
        raise SSFExceptionApplicationModuleError(
            "Application module has missing interfaces"
        )

    return ssf_config.application.interface


def get_application_test(ssf_config: SSFConfig):
    # NOTE:
    # This creates and returns an instance of the application test if it exists, or None.
    # It is NOT cached.
    logger = logging.getLogger("ssf")
    # SSFApplicationTestInterface is still executed from SSF main process
    # Path is edited so import only "see" new modules from app_env
    # This approach is limited to modules that aren't already imported (cached)
    version = sys.version_info
    # Adding app venv site-package to path
    sys.path.append(
        os.path.join(
            ssf_config.application.venv_dir,
            "lib",
            f"python{version[0]}.{version[1]}",
            "site-packages",
        )
    )

    # Removing previous env site-packages
    for path in sys.path:
        if sys.prefix in path and "packages" in path:
            sys.path.remove(path)

    test_interface = instantiate_application(
        ssf_config,
        app_cls="SSFApplicationTestInterface",
        factory_fn="create_ssf_application_test_instance",
        debug_name="test interface",
    )

    if test_interface is not None:
        OK = True
        OK = check_interface(test_interface, "begin", logger) and OK
        OK = check_interface(test_interface, "subtest", logger) and OK
        OK = check_interface(test_interface, "end", logger) and OK
        if not OK:
            raise SSFExceptionApplicationModuleError(
                "Application module has missing test interfaces"
            )

    return test_interface
