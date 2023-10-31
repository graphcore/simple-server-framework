# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import grpc

from ssf.grpc_runtime import grpc_predict_v2_pb2, grpc_predict_v2_pb2_grpc

# SSF is not mandatory to run a client application, required protocol definition.
# Could also be directly imported from proto file.
# grpc_predict_v2_pb2, grpc_predict_v2_pb2_grpc = grpc.protos_and_services("grpc_predict_v2.proto")


_SERVER_ADDR_TEMPLATE = "%s:%d"
_SIGNATURE_HEADER_KEY = "rpc-auth-header"

CLIENT_AUTH_KEY = "test_key"


class KeyAuthClient:
    def __init__(self, address: str, port: int, key: str) -> None:
        # Open insecure channel.
        self.channel = grpc.insecure_channel(_SERVER_ADDR_TEMPLATE % (address, port))

        # Model name / application name is identical to the SSF config YAML application/id value.
        self.model_name = "simple-test"
        self.inference_stub = grpc_predict_v2_pb2_grpc.GRPCInferenceServiceStub(
            self.channel
        )

        # Preformatted auth key header to send to server.
        # The comma after is necessary - the value must be tuple.
        self.metadata = ((_SIGNATURE_HEADER_KEY, key),)

    def send_server_ready_req(self) -> bool:
        """Sends ServerReady request"""

        request = grpc_predict_v2_pb2.ServerReadyRequest()

        try:
            # ServerReadyRequest does not require auth key.
            response, _ = self.inference_stub.ServerReady.with_call(request)
        except grpc.RpcError as rpc_error:
            print(f"RPC ERROR: {rpc_error}")
            raise rpc_error
        else:
            print(f"RECEIVED: {response}")
            return response.ready

    def send_model_ready_req(self) -> bool:
        """Sends ModelReady request"""

        request = grpc_predict_v2_pb2.ModelReadyRequest()

        # Include auth key by attaching metadata.
        request.name = self.model_name

        try:
            # Include authkey in by attaching metadata.
            response, _ = self.inference_stub.ModelReady.with_call(
                request, metadata=self.metadata
            )
        except grpc.RpcError as rpc_error:
            print(f"RPC ERROR: {rpc_error}")
            raise rpc_error
        else:
            print(f"RECEIVED: {response}")
            return response.ready

    def send_inference_req(self, number: int) -> grpc_predict_v2_pb2.ModelInferResponse:
        """Sends ModelInferRequest request

        :param channel: communication channel
        :return: error message or response body
        """

        # The request has to target concrete endpoint of the application.
        # Code below sets endpoint and version to match the values defined in the config YAML file.
        request = grpc_predict_v2_pb2.ModelInferRequest()
        request.parameters["version"].string_param = "1"
        request.parameters["endpoint"].string_param = "Test1"

        # the model always accepts array of values
        values = [number]

        inputs = []
        inputs.append(grpc_predict_v2_pb2.ModelInferRequest().InferInputTensor())
        # Input name must match the one from SSF YAML config.
        inputs[0].name = "x"
        # The size is the length of input vector.
        # tThis model does not support sending more than one value.
        inputs[0].shape.append(len(values))
        # Array of integers must be placed in int_contents.
        inputs[0].contents.int_contents.extend(values)

        request.inputs.extend(inputs)

        try:
            # Include auth key by attaching metadata.
            response, _ = self.inference_stub.ModelInfer.with_call(
                request, metadata=self.metadata
            )
        except grpc.RpcError as rpc_error:
            print(f"RPC ERROR: {rpc_error}")
            raise rpc_error
        else:
            return response


if __name__ == "__main__":
    key_auth_client = KeyAuthClient("localhost", 8100, CLIENT_AUTH_KEY)

    # Make sure the server is ready.
    if not key_auth_client.send_server_ready_req():
        print("Server is not ready to accept requests.")

    # make sure the model is ready.
    if not key_auth_client.send_model_ready_req():
        print("Model is not ready to accept requests.")

    input_number = 101

    # Request inference.
    response = key_auth_client.send_inference_req(input_number)

    print(f"Input value: {input_number}")
    # Full response contains a few outputs.
    # This example extracts description of output and its value.
    for output in response.outputs:
        # The model outputs just one value thus contents.int_contents[0]
        print(
            f"{str(output.parameters['description']).strip()} = {output.contents.int_contents[0]}"
        )
