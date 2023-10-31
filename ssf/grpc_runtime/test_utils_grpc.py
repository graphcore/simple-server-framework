# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import http
import json as js
import logging
import os
from urllib.parse import urlparse

import grpc
import requests

from ssf.common_runtime.common import (
    HEADER_METRICS_DISPATCH_LATENCY,
    HEADER_METRICS_REQUEST_LATENCY,
)

from . import grpc_predict_v2_pb2, grpc_predict_v2_pb2_grpc

logger = logging.getLogger(__name__)

_SERVER_ADDR_TEMPLATE = "%s:%d"


class GRPCNotImplementedError(NotImplementedError):
    NOT_IMPLEMENTED = "Feature not implemented in gRPC test framework."

    def __init__(self, *args: object) -> None:
        super().__init__(self.NOT_IMPLEMENTED, *args)


class GRPCSession:
    def __init__(self, address, port, api_key=None) -> None:
        self.proto_predict_v2 = grpc_predict_v2_pb2
        self.proto_predict_v2_grpc = grpc_predict_v2_pb2_grpc
        self.api_key = None

        self.channel = grpc.insecure_channel(_SERVER_ADDR_TEMPLATE % (address, port))
        self.stub = self.proto_predict_v2_grpc.GRPCInferenceServiceStub(self.channel)

    def gen_inputs_from_json(self, json):
        inputs = []
        for k, v in json.items():
            type_check_element = v
            if isinstance(type_check_element, list):
                if not type_check_element:
                    # user passed empty list in json, nothing to do for ModelInferRequest
                    continue
                type_check_element = v[0]

            values = v if isinstance(v, list) else [v]

            inputs.append(self.proto_predict_v2.ModelInferRequest().InferInputTensor())
            inputs[-1].name = k
            inputs[-1].shape.append(len(values))

            if isinstance(type_check_element, bool):
                # bool is subclass of int keep on top of if ladder
                inputs[-1].contents.bool_contents.extend(values)
            elif isinstance(type_check_element, int):
                inputs[-1].contents.int_contents.extend(values)
            elif isinstance(type_check_element, float):
                inputs[-1].contents.fp64_contents.extend(values)
            elif isinstance(type_check_element, str):
                values_encoded = [bytes(elt, "UTF-8") for elt in values]
                inputs[-1].contents.bytes_contents.extend(values_encoded)
            else:
                raise GRPCNotImplementedError(
                    f"Input type {type(type_check_element)} not supported."
                )

        return inputs

    def gen_inputs_from_files(self, files):
        inputs = []

        for k, v in files.items():
            file_name = v[0]
            file_buffer = v[1]
            inputs.append(self.proto_predict_v2.ModelInferRequest().InferInputTensor())
            inputs[-1].name = k
            inputs[-1].shape.append(len(files))
            inputs[-1].contents.bytes_contents.append(file_buffer.read())
            inputs[-1].parameters["file_name"].string_param = file_name

        return inputs

    def get(self, url, params=None, **kwargs):
        """Mimics signature and functionality of `request' module `get`."""

        p_url = urlparse(url)

        if "/health/ready" in p_url.path:
            logger.debug("gRPC Session ServerReadyRequest()")
            request = self.proto_predict_v2.ServerReadyRequest()
            stub_response = requests.Response()

            try:
                response, _ = self.stub.ServerReady.with_call(request)
                logger.debug(f"gRPC Session ServerReadyResponse {response}")
                stub_response.status_code = (
                    http.HTTPStatus.OK
                    if response.ready
                    else http.HTTPStatus.SERVICE_UNAVAILABLE
                )

            except grpc.RpcError as rpc_error:
                stub_response.status_code = http.HTTPStatus.UNAUTHORIZED

            return stub_response

        elif p_url.netloc and not p_url.path:
            logger.debug("gRPC Session channel connection check request.")
            # emulated root endpoint call checks gRPC communication status
            stub_response = requests.Response()
            try:
                grpc.channel_ready_future(self.channel).result(timeout=1)
                stub_response.status_code = http.HTTPStatus.OK
                stub_response._content = bytes('{"message":"OK"}', "ascii")
                return stub_response
            except grpc.FutureTimeoutError:
                stub_response.status_code = http.HTTPStatus.SERVICE_UNAVAILABLE
                return stub_response

        elif "logout" in p_url.path:
            self.api_key = None

            logger.debug("gRPC Session logout.")
            stub_response_history = requests.Response()
            stub_response_history.status_code = http.HTTPStatus.TEMPORARY_REDIRECT

            stub_response = requests.Response()
            stub_response.status_code = http.HTTPStatus.OK
            stub_response._content = bytes('{"message":"OK"}', "ascii")
            stub_response.history.append(stub_response_history)

            return stub_response

        elif "login" in p_url.path:
            logger.debug("gRPC Session login call.")
            stub_response = requests.Response()
            stub_response.status_code = http.HTTPStatus.FORBIDDEN
            stub_response._content = bytes("Invalid credentials", "ascii")

            if params and "api_key" in params:
                api_key = params["api_key"]

                request = self.proto_predict_v2.ModelReadyRequest()
                try:
                    response, _ = self.stub.ModelReady.with_call(
                        request, metadata=(("rpc-auth-header", api_key),)
                    )

                    stub_response_history = requests.Response()
                    stub_response_history.status_code = (
                        http.HTTPStatus.TEMPORARY_REDIRECT
                    )

                    stub_response.status_code = http.HTTPStatus.OK
                    stub_response._content = bytes('{"message":"OK"}', "ascii")
                    stub_response.history.append(stub_response_history)

                    self.api_key = api_key
                    logger.debug(f"gRPC Session setting key to {self.api_key}")

                except grpc.RpcError as rpc_error:
                    if rpc_error.code() != grpc.StatusCode.UNAUTHENTICATED:
                        raise rpc_error
                    logger.debug(f"gRPC Session request rejected with key {api_key}")
            else:
                logger.debug(
                    f"gRPC Session login called but no api key. Kwargs: {kwargs}; Params {params}"
                )

            return stub_response

        raise GRPCNotImplementedError(f"Unknown `get` request.")

    def grpc_send_infer_request(
        self, version, endpoint, input_dict
    ) -> grpc_predict_v2_pb2.ModelInferResponse:
        """Sends pure gRPC ModelInferRequest request

        Args:
            endpoint (str): Endpoint name
            version (str): Endpoint version
            input_dict (dict): inputs in form of dictinary i.e. {"x" : 2, "y" : "add"}

        Returns:
            response (ModelInferResponse): api response
        """
        request = self.proto_predict_v2.ModelInferRequest()
        request.parameters["version"].string_param = version
        request.parameters["endpoint"].string_param = endpoint
        request.inputs.extend(self.gen_inputs_from_json(input_dict))

        metadata = (("rpc-auth-header", self.api_key),) if self.api_key else None

        response, _ = self.stub.ModelInfer.with_call(request, metadata=metadata)
        return response

    def post(self, url, data=None, json=None, **kwargs):
        """Mimics signature and functionality of `request' module `post`

        Args:
            url (string): See `request` docs
            data (dict, optional): See `request` docs. Defaults to None.
            json (dict, optional): See `request` docs. Defaults to None.
            kwargs: This stub supports arguments - `files` and `params`. See `request` docs.

        Notes:
            Additional non-standard keyworded arguments allow to adjust logic of this stub
            to make up for the ambiguous cases.

            strip_1elt_lists (default: True):
                if True one element lists will be converted to single values in stub HTTP response

        Returns:
            requests.Response: response for the post.
        """
        p_url = urlparse(url)
        p_split = os.path.split(p_url.path)

        request = self.proto_predict_v2.ModelInferRequest()

        # get just version string i.e. '/v1' to 1
        request.parameters["version"].string_param = p_split[0][2:]
        request.parameters["endpoint"].string_param = p_split[1]

        if json:
            request.inputs.extend(self.gen_inputs_from_json(json))

        params = kwargs.get("params", None)
        if params:
            request.inputs.extend(self.gen_inputs_from_json(params))

        files = kwargs.get("files", None)
        if files:
            request.inputs.extend(self.gen_inputs_from_files(files))

        # FastAPI a expects either list of size 1 or just value which are
        # indistinguishable cases for gRPC since it is always list.
        # By default stub will always default to value only.
        # Mixed cases tests will have to be excluded.
        strip_1elt_lists = kwargs.get("strip_1elt_lists", True)

        metadata = (("rpc-auth-header", self.api_key),) if self.api_key else None
        if self.api_key:
            logger.debug(f"gRPC Session using api key {self.api_key}")

        response, _ = self.stub.ModelInfer.with_call(
            request, timeout=kwargs.get("timeout", None), metadata=metadata
        )

        stub_response = requests.Response()
        stub_response.status_code = http.HTTPStatus.OK

        stub_response_text = {}
        stub_response_binary = {}
        if hasattr(response, "outputs"):
            for output in response.outputs:
                ret_val_decoded = []
                stub_response_target = stub_response_text
                if output.datatype == "INT32":
                    ret_val_decoded = [elt for elt in output.contents.int_contents]
                elif output.datatype == "FP64":
                    ret_val_decoded = [elt for elt in output.contents.fp64_contents]
                elif output.datatype == "BOOL":
                    ret_val_decoded = [elt for elt in output.contents.bool_contents]
                elif output.datatype == "BYTE_STRING":
                    ret_val = output.contents.bytes_contents
                    while len(ret_val):
                        # pop instead of list comprehension to free the memory on the fly
                        ret_val_decoded.append(ret_val.pop(0).decode())
                elif output.datatype == "BYTES":
                    ret_val = output.contents.bytes_contents
                    while len(ret_val):
                        # pop instead of list comprehension to free the memory on the fly
                        ret_val_decoded.append(ret_val.pop(0))
                    stub_response_target = stub_response_binary
                else:
                    raise GRPCNotImplementedError(
                        f"Unknown type {output.datatype} for output {output.name} of {url}"
                    )

                strip_list = len(ret_val_decoded) == 1 and strip_1elt_lists
                stub_response_target[output.name] = (
                    ret_val_decoded[0] if strip_list else ret_val_decoded
                )

        if len(stub_response_binary) > 1:
            raise ValueError("Multiple output files not supported in FastAPI")

        if stub_response_text and stub_response_binary:
            for k, v in stub_response_text.items():
                # str since all headers are stringified
                stub_response.headers[k] = str(v)
        elif stub_response_text:
            # text only response, encode all in contents
            stub_response._content = bytes(
                js.dumps(stub_response_text, separators=(",", ":")), "ascii"
            )
            stub_response.encoding = "ascii"

        if stub_response_binary:
            stub_response._content = list(stub_response_binary.values())[0]

        stub_response.headers[HEADER_METRICS_REQUEST_LATENCY] = response.parameters[
            HEADER_METRICS_REQUEST_LATENCY
        ].string_param
        stub_response.headers[HEADER_METRICS_DISPATCH_LATENCY] = response.parameters[
            HEADER_METRICS_DISPATCH_LATENCY
        ].string_param

        return stub_response
