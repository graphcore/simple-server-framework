# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import logging
import time
import grpc

from ssf.common_runtime.common import (
    HEADER_METRICS_DISPATCH_LATENCY,
    HEADER_METRICS_REQUEST_LATENCY,
)
from ssf.results import (
    SSFExceptionGRPCAppConfigError,
    SSFExceptionGRPCRequestError,
    SSFExceptionGRPCSSFError,
)

from ssf.version import NAME, VERSION

from . import grpc_predict_v2_pb2, grpc_predict_v2_pb2_grpc
from .grpc_common import (
    request_endpoint_parameter,
    request_version_parameter,
)
from .grpc_types import create_io_handler, is_type_supported

logger = logging.getLogger("ssf")


class GRPCService(grpc_predict_v2_pb2_grpc.GRPCInferenceServiceServicer):
    def __init__(self, applications) -> None:
        self.applications = applications
        self.application_ids = self.applications.get_applications_ids()
        self.type_check()
        super().__init__()

    def type_check(self):
        """Checks if all types in YAML can be properly served.
        This check shall be performed while application starts to avoid
        crash of application during runtime when responses are dynamically
        created.
        """
        for app_config in self.applications.ssf_config_list:
            for endpoint in app_config.endpoints:
                for app_input in endpoint.inputs:
                    if not is_type_supported(app_input, False):
                        raise SSFExceptionGRPCAppConfigError(
                            f"Input type {app_input.dtype} is not supported."
                        )
                for app_output in endpoint.outputs:
                    if not is_type_supported(app_output, True):
                        raise SSFExceptionGRPCAppConfigError(
                            f"Output type {app_output.dtype} is not supported."
                        )

    def grpc_call_wrapper(func):
        """Helper decorator to properly report exceptions.
        Can be used to wrap gRPC handlers.
        """

        def wrapper(*args, **kw):
            server, request, context = args
            response = None
            try:
                response = func(*args)
            except SSFExceptionGRPCRequestError as e:
                context.set_details(e.user_message)
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            except Exception as e:
                context.set_code(grpc.StatusCode.INTERNAL)
                raise SSFExceptionGRPCSSFError() from e
            finally:
                if response:
                    return response
                else:
                    return grpc_predict_v2_pb2.ModelInferResponse()

        return wrapper

    @grpc_call_wrapper
    def ModelInfer(self, request, context):
        request.model_name = self.get_application_name(request.model_name)

        if self.applications.dispatcher[request.model_name].is_ready():
            return self._model_infer_handler(request, context)
        else:
            context.set_details(f"Model {request.model_name} not ready.")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return grpc_predict_v2_pb2.ModelInferResponse()

    @grpc_call_wrapper
    def ModelReady(self, request, context):
        app_name = self.get_application_name(request.name)
        return grpc_predict_v2_pb2.ModelReadyResponse(
            ready=self.applications.dispatcher[app_name].is_ready()
        )

    @grpc_call_wrapper
    def ServerReady(self, request, context):
        return grpc_predict_v2_pb2.ServerReadyResponse(
            ready=self.applications.is_ready()
        )

    @grpc_call_wrapper
    def ServerLive(self, request, context):
        # responds True as soon as the server can respond gRPC request
        return grpc_predict_v2_pb2.ServerLiveResponse(live=True)

    @grpc_call_wrapper
    def ServerMetadata(self, request, context):
        return grpc_predict_v2_pb2.ServerMetadataResponse(name=NAME, version=VERSION)

    def _model_infer_handler(self, request, context):
        application_idx = self.application_ids.index(request.model_name)
        application_config = self.applications.ssf_config_list[application_idx]

        # check what endpoint is targeted
        app_endpoint_idx = self.get_application_endpoint_idx(
            request, application_config
        )
        app_endpoint = application_config.endpoints[app_endpoint_idx]

        request_meta_dict = {
            "endpoint_id": app_endpoint.id,
            "endpoint_version": app_endpoint.version,
            "endpoint_index": app_endpoint_idx,
        }

        # life of request_param_handlers objects shall be maintained until the
        # application request is processed due to possible temporary objects
        # tight with the lifespan of handler
        request_param_handlers = []
        request_params_dict = {}

        # create input handlers
        for app_input in app_endpoint.inputs:
            input_idx = self.get_request_input_idx_by_name(request, app_input)
            input_handler = create_io_handler(
                request.inputs[input_idx], app_input, request.model_name
            )
            request_param_handlers.append(input_handler)

        # create request
        for handler in request_param_handlers:
            request_params_dict[handler.get_input_id()] = handler.get_input()

        # process requests
        self.applications.dispatcher[request.model_name].queue_request(
            (request_params_dict, request_meta_dict)
        )
        results = self.applications.dispatcher[request.model_name].get_result()

        response = grpc_predict_v2_pb2.ModelInferResponse()
        response.model_name = request.model_name

        if results:
            # create output handlers
            output_handlers = []
            outputs = []
            for app_output in app_endpoint.outputs:
                output_handlers.append(
                    create_io_handler(None, app_output, request.model_name)
                )

            for handler in output_handlers:
                outputs.append(handler.get_output(results))

            response.outputs.extend(outputs)
            dispatch_latency = str(results[HEADER_METRICS_DISPATCH_LATENCY])
            response.parameters[HEADER_METRICS_DISPATCH_LATENCY].string_param = str(
                dispatch_latency
            )
            logger.info(f"> {request.model_name} results {results.keys()}")

        else:
            dispatch_latency = "NA"
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)

        logger.info(f"> {request.model_name} leave ({dispatch_latency})")

        return response

    def get_application_name(self, name):
        if not name and len(self.application_ids) == 1:
            return self.application_ids[0]

        if name in self.application_ids:
            return name

        available_applications = f"Available models: {' '.join(self.application_ids)}"

        if name:
            error_str = f"Unsupported model {name}. {available_applications}"
        else:
            error_str = f"Model name not set. {available_applications}"

        raise SSFExceptionGRPCRequestError(error_str)

    def get_application_endpoint_idx(
        self, request: grpc_predict_v2_pb2.ModelInferRequest, application_config
    ):
        """Given gRPC request get the endpoint index from SSF config.
        Throw if unexistent endpoint name provided.

        For ease of use if the choice is non-ambiguous default to it.
        """
        endpoint_id = str()
        endpoint_version = str()

        application_endpoint_ids = set(
            [endpoint.id for endpoint in application_config.endpoints]
        )
        application_endpoint_versions = []

        endpoint_id = request.parameters.get(request_endpoint_parameter, None)
        endpoint_id = endpoint_id.string_param if endpoint_id else None
        if not endpoint_id and len(application_endpoint_ids) == 1:
            endpoint_id = application_config.endpoints[0].id

        if endpoint_id:
            application_endpoint_versions = [
                str(endpoint.version)
                for endpoint in application_config.endpoints
                if endpoint.id == endpoint_id
            ]

        if application_endpoint_versions:
            endpoint_version = request.parameters.get(request_version_parameter, None)
            endpoint_version = (
                endpoint_version.string_param if endpoint_version else None
            )
            if not endpoint_version and len(application_endpoint_versions) == 1:
                endpoint_version = application_endpoint_versions[0]

        if not endpoint_id:
            raise SSFExceptionGRPCRequestError(
                f"Specify endpoint id with 'endpoint' parameter (string_param). Choice: {' '.join(application_endpoint_ids)}"
            )

        if endpoint_id not in application_endpoint_ids:
            raise SSFExceptionGRPCRequestError(
                f"Endpoint '{endpoint_id}' not found. Choice: {' '.join(application_endpoint_ids)}"
            )

        if not endpoint_version:
            raise SSFExceptionGRPCRequestError(
                f"Specify endpoint version with 'version' parameter (string_param). Choice: {' '.join(application_endpoint_versions)}"
            )

        if endpoint_version not in application_endpoint_versions:
            raise SSFExceptionGRPCRequestError(
                f"Endpoint version '{endpoint_version}' of endpoint '{endpoint_id}' not found. Choice: {' '.join(application_endpoint_versions)}"
            )

        for idx, endpoint in enumerate(application_config.endpoints):
            if str(endpoint.version) == endpoint_version and endpoint.id == endpoint_id:
                return idx

        raise Exception(
            f"BUG: Endpoint version '{endpoint_version}' of endpoint '{endpoint_id}' not found."
        )

    def get_request_input_idx_by_name(self, request, app_input):
        """Given application input from SSF config get the index of corresponding gRPC request input.
        Throw if request lacks expected input.
        """
        if not request.inputs:
            raise SSFExceptionGRPCRequestError(f"Inputs not set in request.")

        for idx, input in enumerate(request.inputs):
            if input.name != app_input.id:
                continue

            return idx

        raise SSFExceptionGRPCRequestError(
            f"Input name = '{app_input.id}', type = '{app_input.dtype}' not found"
        )
