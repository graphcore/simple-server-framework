# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import os
from collections.abc import Iterable
from dataclasses import dataclass
from tempfile import NamedTemporaryFile

from ssf.results import (
    SSFExceptionGRPCAppConfigError,
    SSFExceptionGRPCRequestError,
)

from . import grpc_predict_v2_pb2
from .grpc_common import *

from grpc import StatusCode


@dataclass
class SSFTypeHandler:

    user_request_input: grpc_predict_v2_pb2.ModelInferRequest.InferInputTensor
    ssf_io: dict
    model_name: str
    is_list: bool

    def __post_init__(self):
        if self.user_request_input:
            self.user_request_verify()
            self.user_request_consume()

    def get_input_id(self):
        return self.ssf_io.id

    def get_input_desc(self):
        return self.ssf_io.description

    def check_content(self, grpc_type):
        """Helper function to verify if grpc_predict_v2_pb2.ModelInferRequest.InferInputTensor
        contains contents type of given type.

        :param grpc_type: Expected type of contents in InferTensorContents
        :raises SSFException
        """

        if grpc_type == grpc_type_contents_bytes:
            if (
                self.user_request_input.contents.bytes_contents
                and len(self.user_request_input.contents.bytes_contents[0]) != 0
            ):
                return
        else:
            try:
                if getattr(self.user_request_input.contents, grpc_type):
                    return
            except AttributeError:
                pass

        raise SSFExceptionGRPCRequestError(
            f"contents.{grpc_type} not set in input name = '{self.user_request_input.name}'."
        )

    def check_parameter(self, parameter_name, parameter_type):
        """Helper function to verify if request contains given parameter.

        :param parameter_name: Name of the parameter to check.
        :param parameter_type: Expected type contained in grpc_predict_v2_pb2.InferParameter
        :return: The value of requested parameter.
        """

        if parameter_type == "string_param":
            value = self.user_request_input.parameters[parameter_name].string_param
        elif parameter_type == "int64_param":
            value = self.user_request_input.parameters[parameter_name].int64_param
        elif parameter_type == "bool_param":
            value = self.user_request_input.parameters[parameter_name].bool_param
        else:
            raise SSFExceptionGRPCAppConfigError(
                f"Type {parameter_type} of input {self.get_input_id()} is invalid.",
            )

        if value:
            return value
        raise SSFExceptionGRPCRequestError(
            f"'{parameter_name}' not set in parameters {parameter_type} of input '{self.user_request_input.name}'."
        )

    def build_output_contents(
        self, content_type: str, tensor_data_type: str, content_value
    ):
        """Helper function for creating the output tensor.

        :param content_type: type of grpc_predict_v2_pb2.ModelInferRequest.InferInputTensor
        :param tensor_data_type: name of type provided for the user (useful in case of 'bytes_contents' for interpretation hint)
        :param content_value: value to be stored in contents
        :return: Output tensor
        """

        if not hasattr(self, "output_tensor"):
            self.output_tensor = (
                grpc_predict_v2_pb2.ModelInferResponse().InferOutputTensor()
            )

        if tensor_data_type:
            self.output_tensor.datatype = tensor_data_type

        self.output_tensor.name = self.get_input_id()
        self.output_tensor.parameters[
            response_parameter_description
        ].string_param = self.get_input_desc()

        if isinstance(content_value, list):
            self.output_tensor.shape.extend([len(content_value)])
            getattr(self.output_tensor.contents, content_type).extend(content_value)
        else:
            self.output_tensor.shape.extend([1])
            getattr(self.output_tensor.contents, content_type).append(content_value)

        return self.output_tensor

    def user_request_verify(self):
        """Verify if gRPC request contains all expected fields.
        User problems must be reported using SSFException.

        Leave default implementation for output only type.

        :raises SSFException
        """

        raise SSFExceptionGRPCAppConfigError(
            f"Type {self.__name__} unsupported for input."
        )

    def user_request_consume(self):
        """Consume the part of grpc_predict_v2_pb2.ModelInferRequest.InferInputTensor that
        contains input data.

        Leave default implementation for output only type.

        :raises SSFException
        """

        raise SSFExceptionGRPCAppConfigError(
            f"Class {self.__name__} unsupported for input."
        )

    def get_input(self):
        """Returns the value that will be input to the model.

        Leave default implementation for output only type.

        :raises SSFException
        """

        raise SSFExceptionGRPCAppConfigError(
            f"Class {self.__name__} unsupported for input."
        )

    def get_output(self, app_result):
        """Returns value grpc_predict_v2_pb2.ModelInferResponse().InferOutputTensor() that
        is output of model processing.

        :param app_result: dictionary that has been returned from the model
        :raises SSFException
        """

        raise SSFExceptionGRPCAppConfigError(
            f"Class {self.__name__} unsupported for output."
        )


@dataclass
class SSFTypeHandlerFile(SSFTypeHandler):
    require_extension: bool = True

    def user_request_verify(self):
        self.check_content(grpc_type_contents_bytes)
        filename = self.check_parameter(request_filename_parameter, "string_param")

        if self.require_extension:
            _, self.extension = os.path.splitext(filename)

            if not self.extension:
                raise SSFExceptionGRPCRequestError(
                    f"Filename '{filename}' of parameter '{self.user_request_input.name}' must contain extension."
                )

    def user_request_consume(self):
        extension = self.extension if hasattr(self, "extension") else "tmp"
        self.tempfile = NamedTemporaryFile(
            prefix=self.model_name, suffix=f".{extension}"
        )
        fp = open(self.tempfile.name, "wb")
        # after calling pop bytes_contents will become unusable
        fp.write(self.user_request_input.contents.bytes_contents.pop())
        fp.close()

    def get_input(self):
        return self.tempfile.name

    def get_output(self, app_result):
        return self.build_output_contents(
            grpc_type_contents_bytes,
            grpc_tensor_datatype_bytes,
            app_result[self.get_input_id()],
        )


@dataclass
class SSFTypeHandlerBasicContent(SSFTypeHandler):
    tensor_datatype: str

    def user_request_verify(self):
        self.check_content(tensor_to_grpc_type[self.tensor_datatype])

    def user_request_consume(self):
        container = getattr(
            self.user_request_input.contents, tensor_to_grpc_type[self.tensor_datatype]
        )
        if self.is_list:
            self.value = []
            while len(container):
                self.value.append(container.pop(0))
        else:
            self.value = container.pop()

    def get_input(self):
        return self.value

    def get_output(self, app_result):
        return self.build_output_contents(
            tensor_to_grpc_type[self.tensor_datatype],
            self.tensor_datatype,
            app_result[self.get_input_id()],
        )


@dataclass
class SSFTypeHandlerStringContent(SSFTypeHandler):
    def user_request_verify(self):
        self.check_content(grpc_type_contents_bytes)

    def user_request_consume(self):
        container = self.user_request_input.contents.bytes_contents
        if self.is_list:
            self.value = []
            while len(container):
                # pop instead of list comprehension to free the memory on the fly
                self.value.append(container.pop(0).decode())
        else:
            self.value = container.pop().decode()

    def get_input(self):
        return self.value

    def get_output(self, app_result):
        # casting to string to support some compatibility with `Any` and `ListAny`

        if self.is_list:
            content_encoded = [
                bytes(str(elt), "UTF-8") for elt in app_result[self.get_input_id()]
            ]
        else:
            content_encoded = bytes(str(app_result[self.get_input_id()]), "UTF-8")
        return self.build_output_contents(
            grpc_type_contents_bytes, grpc_tensor_datatype_string, content_encoded
        )


type_handlers = {
    "String": {"handler_type": SSFTypeHandlerStringContent},
    "ListString": {"handler_type": SSFTypeHandlerStringContent},
    "Boolean": {
        "handler_type": SSFTypeHandlerBasicContent,
        "handler_params": [grpc_tensor_datatype_bool],
    },
    "ListBoolean": {
        "handler_type": SSFTypeHandlerBasicContent,
        "handler_params": [grpc_tensor_datatype_bool],
    },
    "Integer": {
        "handler_type": SSFTypeHandlerBasicContent,
        "handler_params": [grpc_tensor_datatype_int32],
    },
    "ListInteger": {
        "handler_type": SSFTypeHandlerBasicContent,
        "handler_params": [grpc_tensor_datatype_int32],
    },
    "Float": {
        "handler_type": SSFTypeHandlerBasicContent,
        "handler_params": [grpc_tensor_datatype_fp64],
    },
    "ListFloat": {
        "handler_type": SSFTypeHandlerBasicContent,
        "handler_params": [grpc_tensor_datatype_fp64],
    },
    "TempFile": {"handler_type": SSFTypeHandlerFile},
    "PngImageBytes": {"handler_type": SSFTypeHandlerFile},
}


def create_io_handler(request_input, ssf_io, model_name) -> SSFTypeHandler:
    if ssf_io.dtype in type_handlers:
        handler_config = type_handlers[ssf_io.dtype]
        params = [request_input, ssf_io, model_name, "List" in ssf_io.dtype]
        if "handler_params" in handler_config:
            params.extend(handler_config["handler_params"])
        return handler_config["handler_type"](*params)
    else:
        raise SSFExceptionGRPCAppConfigError(
            f"Unsupported input type {request_input.dtype}"
        )


def is_type_supported(ssf_io, is_output):
    if ssf_io.dtype in type_handlers:
        handler_class = type_handlers[ssf_io.dtype]["handler_type"]
        # if output check if type class implement `get_output``
        if (
            is_output
            and handler_class.__name__ in handler_class.get_output.__qualname__
        ):
            return True
        # if input check if type class implement `get_input``
        if (
            not is_output
            and handler_class.__name__ in handler_class.get_input.__qualname__
        ):
            return True

    return False
