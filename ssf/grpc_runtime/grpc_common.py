# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

from dataclasses import dataclass


request_filename_parameter = "file_name"
request_endpoint_parameter = "endpoint"
request_version_parameter = "version"

response_parameter_description = "description"

grpc_tensor_datatype_bytes = "BYTES"
grpc_tensor_datatype_string = "BYTE_STRING"
grpc_tensor_datatype_bool = "BOOL"
grpc_tensor_datatype_int32 = "INT32"
grpc_tensor_datatype_fp64 = "FP64"

grpc_type_contents_bytes = "bytes_contents"
grpc_type_contents_int = "int_contents"
grpc_type_contents_fp64 = "fp64_contents"
grpc_type_contents_bool = "bool_contents"

tensor_to_grpc_type = {
    grpc_tensor_datatype_bytes: grpc_type_contents_bytes,
    grpc_tensor_datatype_string: grpc_type_contents_bytes,
    grpc_tensor_datatype_bool: grpc_type_contents_bool,
    grpc_tensor_datatype_int32: grpc_type_contents_int,
    grpc_tensor_datatype_fp64: grpc_type_contents_fp64,
}
