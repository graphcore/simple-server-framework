# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# NOTE:
# Do not import external packages in application_interface modules
# to avoid introducing additional dependencies for the application.
# Only import SSF modules that are also in application_interface.

from logging import ERROR, WARNING

# Result/exception codes.
# Use a specific derived SSFException**** class to raise errors.

# NOTE:
# The following code section marked between
# '# -- RESULT CODES BEGIN --' and '# -- RESULT CODES END --'
# has specific formatting to support parsing for auto doc generation.
# Comments preceding the RESULT_*** code will be documented for that result code.
# For example:
#   | # <some documented text>
#   | RESULT_EXAMPLE = 100
# Will capture the following to the result codes table: RESULT_EXAMPLE, 100, <some documented text>
# Comments that don't start with '# ' (such as those with a double comment "##") are ignored/dropped.
# Result codes that have zero documented comment lines are NOT documented.

# -- RESULT CODES BEGIN --

# Success/OK.
RESULT_OK = 0

## SSF errors 1:31.

# Misformed or unexpected argument.
RESULT_ARGUMENT_ERROR = 1

# Generic 'failure' code.
RESULT_FAIL = 2

# Unexpected issue within SSF.
RESULT_INTERNAL_ERROR = 3

# Issue with framework generated resources.
RESULT_FRAMEWORK_RESOURCE_ERROR = 4

# Issue with an SSH key or host.
RESULT_SSH_ERROR = 5

# Issue with Docker build.
RESULT_DOCKER_BUILD_ERROR = 6

# Issue with Docker server login or push.
RESULT_DOCKER_SERVER_ERROR = 7

# Issue with Docker status.
RESULT_DOCKER_STATUS_ERROR = 8

# Issue with networking status.
RESULT_NETWORK_ERROR = 9

# Issue installing a dependency.
RESULT_INSTALLATION_ERROR = 10

# Issue deploying an application.
RESULT_DEPLOYMENT_ERROR = 11

# Missing or incomplete feature.
RESULT_NOT_IMPLEMENTED_ERROR = 12

# Issue with accessing git repository.
RESULT_GIT_REPO_ERROR = 13

## Generic application result codes 32:127.

# Issue within the user application.
RESULT_APPLICATION_ERROR = 32

# Failure returned from the user application test.
RESULT_APPLICATION_TEST_ERROR = 33

# Issue within the user application config file.
RESULT_APPLICATION_CONFIG_ERROR = 34

# Issue loading the user application module or creating an application instance.
RESULT_APPLICATION_MODULE_ERROR = 35

# Issue packaging the user application.
RESULT_PACKAGING_ERROR = 36

## FastAPI specific result codes 128:151.

# Issue within the FastAPI Uvicorn runner.
RESULT_UVICORN_ERROR = 128

## gRPC specific result codes 152:175 (placeholder)

# gRPC framework exception
RESULT_GRPC_SERVER_ERROR = 152

# Issue within gRPC logic of SSF
RESULT_GRPC_SSF_ERROR = 153

# Malformed / not correct request
RESULT_GRPC_REQUEST_ERROR = 154

# Application configuration problem
RESULT_GRPC_APP_CONFIG_ERROR = 155

## Deployemnt specific codes

# Paperspace deployment specific issue.
RESULT_PAPERSPACE_DEPLOYMENT_ERROR = 176

# Gcore deployment specific issue.
RESULT_GCORE_DEPLOYMENT_ERROR = 177

## Reserved 224:255 for special cases

# The runner environment does not meet the minimum application requirement.
RESULT_UNMET_REQUIREMENT = 255

## RESULT_SKIPPED for backwards compatability with v1.0
## RESULT_UNMET_REQUIREMENT must be used.
RESULT_SKIPPED = RESULT_UNMET_REQUIREMENT

# -- RESULT CODES END --

# Build a reverse lookup to get string name from result code.
result_strings = {}
local_vars = locals().copy()
for k, v in local_vars.items():
    if k == "RESULT_SKIPPED":
        continue
    if "RESULT_" in k:
        result_strings[v] = k


def result_to_string(result_code):
    return result_strings[result_code]


PREFIX_TEXT = "SSF Exception "
POSTFIX_TEXT = f"ssf.log may contain additional debug information."

# The base SSFException class from which we derive specific coded exceptions.
class SSFException(Exception):
    result_code: int = RESULT_INTERNAL_ERROR

    # By default, derived exceptions expect logger.exception( ) to
    # be used to surface the exception. Alternatively, if the derived
    # exception declares a specific log_with_level then the exception
    # can be suppressed in favour of logger.log( ) at the declared level.
    log_with_level = None

    def __init__(self, *args: object) -> None:
        args = args + (POSTFIX_TEXT,)
        super().__init__(
            f"{PREFIX_TEXT}{result_to_string(self.result_code)} ({self.result_code})",
            *args,
        )


# Errors that are not expected and for which the full stack is output.
# Log level will always be 'ERROR'


class SSFExceptionInternalError(SSFException):
    result_code = RESULT_INTERNAL_ERROR


class SSFExceptionSshError(SSFException):
    result_code = RESULT_SSH_ERROR


class SSFExceptionDockerBuildError(SSFException):
    result_code = RESULT_DOCKER_BUILD_ERROR


class SSFExceptionDockerServerError(SSFException):
    result_code = RESULT_DOCKER_SERVER_ERROR


class SSFExceptionDockerStatusError(SSFException):
    result_code = RESULT_DOCKER_STATUS_ERROR


class SSFExceptionNetworkError(SSFException):
    result_code = RESULT_NETWORK_ERROR


class SSFExceptionInstallationError(SSFException):
    result_code = RESULT_INSTALLATION_ERROR


class SSFExceptionDeploymentError(SSFException):
    result_code = RESULT_DEPLOYMENT_ERROR


class SSFExceptionNotImplementedError(SSFException):
    result_code = RESULT_NOT_IMPLEMENTED_ERROR


class SSFExceptionGitRepoError(SSFException):
    result_code = RESULT_GIT_REPO_ERROR


class SSFExceptionApplicationError(SSFException):
    result_code = RESULT_APPLICATION_ERROR


class SSFExceptionApplicationConfigError(SSFException):
    result_code = RESULT_APPLICATION_CONFIG_ERROR


class SSFExceptionApplicationModuleError(SSFException):
    result_code = RESULT_APPLICATION_MODULE_ERROR


class SSFExceptionPackagingError(SSFException):
    result_code = RESULT_PACKAGING_ERROR


class SSFExceptionUvicornError(SSFException):
    result_code = RESULT_UVICORN_ERROR


class SSFExceptionGRPCServerError(SSFException):
    result_code = RESULT_GRPC_SERVER_ERROR


class SSFExceptionGRPCSSFError(SSFException):
    result_code = RESULT_GRPC_SSF_ERROR


class SSFExceptionGRPCRequestError(SSFException):
    result_code = RESULT_GRPC_REQUEST_ERROR
    user_message: str = "Request error"

    def __init__(self, *args: object) -> None:
        self.user_message = str(args)
        super().__init__(*args)


class SSFExceptionGRPCAppConfigError(SSFException):
    result_code = RESULT_GRPC_APP_CONFIG_ERROR


class SSFExceptionPaperspaceDeploymentError(SSFException):
    result_code = RESULT_PAPERSPACE_DEPLOYMENT_ERROR


class SSFExceptionGcoreDeploymentError(SSFException):
    result_code = RESULT_GCORE_DEPLOYMENT_ERROR


# Errors that are logged but for which the full stack is suppressed.
# The required log level must be set for these.


class SSFExceptionArgumentsError(SSFException):
    result_code = RESULT_ARGUMENT_ERROR
    log_with_level = ERROR


class SSFExceptionFrameworkResourceError(SSFException):
    result_code = RESULT_FRAMEWORK_RESOURCE_ERROR
    log_with_level = ERROR


class SSFExceptionApplicationTestError(SSFException):
    result_code = RESULT_APPLICATION_TEST_ERROR
    log_with_level = ERROR


class SSFExceptionUnmetRequirement(SSFException):
    result_code = RESULT_UNMET_REQUIREMENT
    log_with_level = WARNING
