# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import time
from typing import Awaitable, Callable, Sequence, Union

import grpc
from prometheus_fastapi_instrumentator import metrics
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response

from ssf.common_runtime.common import (
    HEADER_METRICS_DISPATCH_LATENCY,
    HEADER_METRICS_REQUEST_LATENCY,
)


class MetricsInterceptor(grpc.ServerInterceptor):
    def __init__(self, excluded_handlers: Sequence[str], prometheus_disabled):
        # list of handlers not in scope of metrics
        self.excluded_handlers = excluded_handlers
        # list of metric objects to be used
        self.instrumentations = []
        self.prometheus_disabled = prometheus_disabled

    def add(
        self,
        instrumentation_function: Callable[
            [metrics.Info], Union[None, Awaitable[None]]
        ],
    ):
        self.instrumentations.append(instrumentation_function)

    def intercept_service(self, continuation, handler_call_details):

        if handler_call_details.method in self.excluded_handlers:
            return continuation(handler_call_details)

        parts = handler_call_details.method.split("/")
        # i.e. '/inference.GRPCInferenceService/ModelInfer'
        grpc_method_name = "" if len(parts) < 3 else parts[2]

        def _wrap_rpc_hanlder(handler, fn):
            if handler is None:
                return None

            if handler.request_streaming and handler.response_streaming:
                behavior_fn = handler.stream_stream
                handler_factory = grpc.stream_stream_rpc_method_handler
            elif handler.request_streaming and not handler.response_streaming:
                behavior_fn = handler.stream_unary
                handler_factory = grpc.stream_unary_rpc_method_handler
            elif not handler.request_streaming and handler.response_streaming:
                behavior_fn = handler.unary_stream
                handler_factory = grpc.unary_stream_rpc_method_handler
            else:
                behavior_fn = handler.unary_unary
                handler_factory = grpc.unary_unary_rpc_method_handler

            return handler_factory(
                fn(
                    behavior_fn,
                    handler.request_streaming,
                    handler.response_streaming,
                    type(handler_factory),
                ),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        def _metrics_wrapper(
            behavior, request_streaming, response_streaming, handler_type
        ):
            def new_behavior(request_or_iterator, servicer_context):
                start = time.time()
                request_size = 0

                try:
                    if request_or_iterator and getattr(
                        request_or_iterator, "ByteSize", None
                    ):
                        request_size = request_or_iterator.ByteSize()

                    if request_streaming:
                        request_or_iterator = (i for i in request_or_iterator)

                    # original RPC behavior
                    response_or_iterator = behavior(
                        request_or_iterator, servicer_context
                    )

                    if response_streaming:
                        response_or_iterator = (i for i in response_or_iterator)

                    if response_or_iterator and getattr(
                        response_or_iterator, "parameters", None
                    ):
                        response_or_iterator.parameters[
                            HEADER_METRICS_REQUEST_LATENCY
                        ].string_param = str(time.time() - start)

                    return response_or_iterator

                except grpc.RpcError as e:
                    raise e

                finally:
                    if not self.prometheus_disabled:
                        stub_response_headers = {}

                        try:
                            stub_response_headers["Content-Length"] = str(
                                response_or_iterator.ByteSize()
                                if response_or_iterator
                                else 0
                            )
                            dispatch_latency = response_or_iterator.parameters[
                                HEADER_METRICS_DISPATCH_LATENCY
                            ].string_param
                            if dispatch_latency:
                                # if needed since protobuffer will return empty string when key not found
                                stub_response_headers[
                                    HEADER_METRICS_DISPATCH_LATENCY
                                ] = dispatch_latency
                        except:
                            pass

                        modfied_handler = [grpc_method_name]
                        if grpc_method_name == "ModelInfer":
                            modfied_handler.append(request_or_iterator.model_name)
                            modfied_handler.append(
                                "v"
                                + request_or_iterator.parameters["version"].string_param
                            )
                            modfied_handler.append(
                                request_or_iterator.parameters["endpoint"].string_param
                            )

                        # type http necessary for the stub object to be created
                        stub_scope = {"type": "http"}
                        stub_scope["headers"] = Headers(
                            {"Content-Length": str(request_size)}
                        ).raw

                        info = metrics.Info(
                            request=Request(scope=stub_scope),
                            response=Response(headers=stub_response_headers),
                            method=str(handler_type),
                            modified_handler="/".join(modfied_handler),
                            modified_status=servicer_context.code().name
                            if servicer_context.code()
                            else grpc.StatusCode.OK.name,
                            modified_duration=time.time() - start,
                        )
                        for instrumentation in self.instrumentations:
                            instrumentation(info)

            return new_behavior

        metric_wrapped_handler = _wrap_rpc_hanlder(
            continuation(handler_call_details), _metrics_wrapper
        )

        return metric_wrapped_handler
