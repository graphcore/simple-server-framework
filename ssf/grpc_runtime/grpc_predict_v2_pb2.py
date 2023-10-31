# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: ssf/grpc_runtime/grpc_predict_v2.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n&ssf/grpc_runtime/grpc_predict_v2.proto\x12\tinference"\x13\n\x11ServerLiveRequest""\n\x12ServerLiveResponse\x12\x0c\n\x04live\x18\x01 \x01(\x08"\x14\n\x12ServerReadyRequest"$\n\x13ServerReadyResponse\x12\r\n\x05ready\x18\x01 \x01(\x08"2\n\x11ModelReadyRequest\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0f\n\x07version\x18\x02 \x01(\t"#\n\x12ModelReadyResponse\x12\r\n\x05ready\x18\x01 \x01(\x08"\x17\n\x15ServerMetadataRequest"K\n\x16ServerMetadataResponse\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0f\n\x07version\x18\x02 \x01(\t\x12\x12\n\nextensions\x18\x03 \x03(\t"5\n\x14ModelMetadataRequest\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0f\n\x07version\x18\x02 \x01(\t"\x8d\x02\n\x15ModelMetadataResponse\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x10\n\x08versions\x18\x02 \x03(\t\x12\x10\n\x08platform\x18\x03 \x01(\t\x12?\n\x06inputs\x18\x04 \x03(\x0b\x32/.inference.ModelMetadataResponse.TensorMetadata\x12@\n\x07outputs\x18\x05 \x03(\x0b\x32/.inference.ModelMetadataResponse.TensorMetadata\x1a?\n\x0eTensorMetadata\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x10\n\x08\x64\x61tatype\x18\x02 \x01(\t\x12\r\n\x05shape\x18\x03 \x03(\x03"\xee\x06\n\x11ModelInferRequest\x12\x12\n\nmodel_name\x18\x01 \x01(\t\x12\x15\n\rmodel_version\x18\x02 \x01(\t\x12\n\n\x02id\x18\x03 \x01(\t\x12@\n\nparameters\x18\x04 \x03(\x0b\x32,.inference.ModelInferRequest.ParametersEntry\x12=\n\x06inputs\x18\x05 \x03(\x0b\x32-.inference.ModelInferRequest.InferInputTensor\x12H\n\x07outputs\x18\x06 \x03(\x0b\x32\x37.inference.ModelInferRequest.InferRequestedOutputTensor\x12\x1a\n\x12raw_input_contents\x18\x07 \x03(\x0c\x1a\x94\x02\n\x10InferInputTensor\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x10\n\x08\x64\x61tatype\x18\x02 \x01(\t\x12\r\n\x05shape\x18\x03 \x03(\x03\x12Q\n\nparameters\x18\x04 \x03(\x0b\x32=.inference.ModelInferRequest.InferInputTensor.ParametersEntry\x12\x30\n\x08\x63ontents\x18\x05 \x01(\x0b\x32\x1e.inference.InferTensorContents\x1aL\n\x0fParametersEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12(\n\x05value\x18\x02 \x01(\x0b\x32\x19.inference.InferParameter:\x02\x38\x01\x1a\xd5\x01\n\x1aInferRequestedOutputTensor\x12\x0c\n\x04name\x18\x01 \x01(\t\x12[\n\nparameters\x18\x02 \x03(\x0b\x32G.inference.ModelInferRequest.InferRequestedOutputTensor.ParametersEntry\x1aL\n\x0fParametersEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12(\n\x05value\x18\x02 \x01(\x0b\x32\x19.inference.InferParameter:\x02\x38\x01\x1aL\n\x0fParametersEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12(\n\x05value\x18\x02 \x01(\x0b\x32\x19.inference.InferParameter:\x02\x38\x01"\xd5\x04\n\x12ModelInferResponse\x12\x12\n\nmodel_name\x18\x01 \x01(\t\x12\x15\n\rmodel_version\x18\x02 \x01(\t\x12\n\n\x02id\x18\x03 \x01(\t\x12\x41\n\nparameters\x18\x04 \x03(\x0b\x32-.inference.ModelInferResponse.ParametersEntry\x12@\n\x07outputs\x18\x05 \x03(\x0b\x32/.inference.ModelInferResponse.InferOutputTensor\x12\x1b\n\x13raw_output_contents\x18\x06 \x03(\x0c\x1a\x97\x02\n\x11InferOutputTensor\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x10\n\x08\x64\x61tatype\x18\x02 \x01(\t\x12\r\n\x05shape\x18\x03 \x03(\x03\x12S\n\nparameters\x18\x04 \x03(\x0b\x32?.inference.ModelInferResponse.InferOutputTensor.ParametersEntry\x12\x30\n\x08\x63ontents\x18\x05 \x01(\x0b\x32\x1e.inference.InferTensorContents\x1aL\n\x0fParametersEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12(\n\x05value\x18\x02 \x01(\x0b\x32\x19.inference.InferParameter:\x02\x38\x01\x1aL\n\x0fParametersEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12(\n\x05value\x18\x02 \x01(\x0b\x32\x19.inference.InferParameter:\x02\x38\x01"i\n\x0eInferParameter\x12\x14\n\nbool_param\x18\x01 \x01(\x08H\x00\x12\x15\n\x0bint64_param\x18\x02 \x01(\x03H\x00\x12\x16\n\x0cstring_param\x18\x03 \x01(\tH\x00\x42\x12\n\x10parameter_choice"\xd0\x01\n\x13InferTensorContents\x12\x15\n\rbool_contents\x18\x01 \x03(\x08\x12\x14\n\x0cint_contents\x18\x02 \x03(\x05\x12\x16\n\x0eint64_contents\x18\x03 \x03(\x03\x12\x15\n\ruint_contents\x18\x04 \x03(\r\x12\x17\n\x0fuint64_contents\x18\x05 \x03(\x04\x12\x15\n\rfp32_contents\x18\x06 \x03(\x02\x12\x15\n\rfp64_contents\x18\x07 \x03(\x01\x12\x16\n\x0e\x62ytes_contents\x18\x08 \x03(\x0c\x32\xfc\x03\n\x14GRPCInferenceService\x12K\n\nServerLive\x12\x1c.inference.ServerLiveRequest\x1a\x1d.inference.ServerLiveResponse"\x00\x12N\n\x0bServerReady\x12\x1d.inference.ServerReadyRequest\x1a\x1e.inference.ServerReadyResponse"\x00\x12K\n\nModelReady\x12\x1c.inference.ModelReadyRequest\x1a\x1d.inference.ModelReadyResponse"\x00\x12W\n\x0eServerMetadata\x12 .inference.ServerMetadataRequest\x1a!.inference.ServerMetadataResponse"\x00\x12T\n\rModelMetadata\x12\x1f.inference.ModelMetadataRequest\x1a .inference.ModelMetadataResponse"\x00\x12K\n\nModelInfer\x12\x1c.inference.ModelInferRequest\x1a\x1d.inference.ModelInferResponse"\x00\x62\x06proto3'
)

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(
    DESCRIPTOR, "ssf.grpc_runtime.grpc_predict_v2_pb2", globals()
)
if _descriptor._USE_C_DESCRIPTORS == False:

    DESCRIPTOR._options = None
    _MODELINFERREQUEST_INFERINPUTTENSOR_PARAMETERSENTRY._options = None
    _MODELINFERREQUEST_INFERINPUTTENSOR_PARAMETERSENTRY._serialized_options = b"8\001"
    _MODELINFERREQUEST_INFERREQUESTEDOUTPUTTENSOR_PARAMETERSENTRY._options = None
    _MODELINFERREQUEST_INFERREQUESTEDOUTPUTTENSOR_PARAMETERSENTRY._serialized_options = (
        b"8\001"
    )
    _MODELINFERREQUEST_PARAMETERSENTRY._options = None
    _MODELINFERREQUEST_PARAMETERSENTRY._serialized_options = b"8\001"
    _MODELINFERRESPONSE_INFEROUTPUTTENSOR_PARAMETERSENTRY._options = None
    _MODELINFERRESPONSE_INFEROUTPUTTENSOR_PARAMETERSENTRY._serialized_options = b"8\001"
    _MODELINFERRESPONSE_PARAMETERSENTRY._options = None
    _MODELINFERRESPONSE_PARAMETERSENTRY._serialized_options = b"8\001"
    _SERVERLIVEREQUEST._serialized_start = 53
    _SERVERLIVEREQUEST._serialized_end = 72
    _SERVERLIVERESPONSE._serialized_start = 74
    _SERVERLIVERESPONSE._serialized_end = 108
    _SERVERREADYREQUEST._serialized_start = 110
    _SERVERREADYREQUEST._serialized_end = 130
    _SERVERREADYRESPONSE._serialized_start = 132
    _SERVERREADYRESPONSE._serialized_end = 168
    _MODELREADYREQUEST._serialized_start = 170
    _MODELREADYREQUEST._serialized_end = 220
    _MODELREADYRESPONSE._serialized_start = 222
    _MODELREADYRESPONSE._serialized_end = 257
    _SERVERMETADATAREQUEST._serialized_start = 259
    _SERVERMETADATAREQUEST._serialized_end = 282
    _SERVERMETADATARESPONSE._serialized_start = 284
    _SERVERMETADATARESPONSE._serialized_end = 359
    _MODELMETADATAREQUEST._serialized_start = 361
    _MODELMETADATAREQUEST._serialized_end = 414
    _MODELMETADATARESPONSE._serialized_start = 417
    _MODELMETADATARESPONSE._serialized_end = 686
    _MODELMETADATARESPONSE_TENSORMETADATA._serialized_start = 623
    _MODELMETADATARESPONSE_TENSORMETADATA._serialized_end = 686
    _MODELINFERREQUEST._serialized_start = 689
    _MODELINFERREQUEST._serialized_end = 1567
    _MODELINFERREQUEST_INFERINPUTTENSOR._serialized_start = 997
    _MODELINFERREQUEST_INFERINPUTTENSOR._serialized_end = 1273
    _MODELINFERREQUEST_INFERINPUTTENSOR_PARAMETERSENTRY._serialized_start = 1197
    _MODELINFERREQUEST_INFERINPUTTENSOR_PARAMETERSENTRY._serialized_end = 1273
    _MODELINFERREQUEST_INFERREQUESTEDOUTPUTTENSOR._serialized_start = 1276
    _MODELINFERREQUEST_INFERREQUESTEDOUTPUTTENSOR._serialized_end = 1489
    _MODELINFERREQUEST_INFERREQUESTEDOUTPUTTENSOR_PARAMETERSENTRY._serialized_start = (
        1197
    )
    _MODELINFERREQUEST_INFERREQUESTEDOUTPUTTENSOR_PARAMETERSENTRY._serialized_end = 1273
    _MODELINFERREQUEST_PARAMETERSENTRY._serialized_start = 1197
    _MODELINFERREQUEST_PARAMETERSENTRY._serialized_end = 1273
    _MODELINFERRESPONSE._serialized_start = 1570
    _MODELINFERRESPONSE._serialized_end = 2167
    _MODELINFERRESPONSE_INFEROUTPUTTENSOR._serialized_start = 1810
    _MODELINFERRESPONSE_INFEROUTPUTTENSOR._serialized_end = 2089
    _MODELINFERRESPONSE_INFEROUTPUTTENSOR_PARAMETERSENTRY._serialized_start = 1197
    _MODELINFERRESPONSE_INFEROUTPUTTENSOR_PARAMETERSENTRY._serialized_end = 1273
    _MODELINFERRESPONSE_PARAMETERSENTRY._serialized_start = 1197
    _MODELINFERRESPONSE_PARAMETERSENTRY._serialized_end = 1273
    _INFERPARAMETER._serialized_start = 2169
    _INFERPARAMETER._serialized_end = 2274
    _INFERTENSORCONTENTS._serialized_start = 2277
    _INFERTENSORCONTENTS._serialized_end = 2485
    _GRPCINFERENCESERVICE._serialized_start = 2488
    _GRPCINFERENCESERVICE._serialized_end = 2996
# @@protoc_insertion_point(module_scope)
