# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import grpc

from ssf.grpc_runtime import grpc_predict_v2_pb2, grpc_predict_v2_pb2_grpc

# SSF is not mandatory to run a client application, required protocol definition.
# Could also be directly imported from proto file.
# grpc_predict_v2_pb2, grpc_predict_v2_pb2_grpc = grpc.protos_and_services("grpc_predict_v2.proto")

_SERVER_ADDR_TEMPLATE = "%s:%d"


class MnistClient:
    def __init__(self, address: str, port: int) -> None:
        # Open insecure channel.
        self.channel = grpc.insecure_channel(_SERVER_ADDR_TEMPLATE % (address, port))

        # Model name / application name is identical with SSF config YAML application/id value.
        self.model_name = "mnist_api"
        self.inference_stub = grpc_predict_v2_pb2_grpc.GRPCInferenceServiceStub(
            self.channel
        )

    def send_server_ready_req(self) -> bool:
        """Sends ServerReady request"""

        request = grpc_predict_v2_pb2.ServerReadyRequest()

        try:
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

        # Include name of the model in request.
        request.name = self.model_name

        try:
            response, _ = self.inference_stub.ModelReady.with_call(request)
        except grpc.RpcError as rpc_error:
            print(f"RPC ERROR: {rpc_error}")
            raise rpc_error
        else:
            print(f"RECEIVED: {response}")
            return response.ready

    def send_inference_req(self, image_path: str) -> int:
        """Sends ModelInferRequest request

        Args:
            image_path (str): path to image file

        Returns:
            int: number recognized during inference
        """
        request = grpc_predict_v2_pb2.ModelInferRequest()

        # The request has to target concrete endpoint of application.
        # Code below sets endpoint and version to match the values defined in the config YAML file.
        request.parameters["version"].string_param = "1"
        request.parameters["endpoint"].string_param = "mnist_api"

        inputs = []

        with open(image_path, "rb") as fp:
            inputs.append(grpc_predict_v2_pb2.ModelInferRequest().InferInputTensor())
            # Input name must match the name in the SSF YAML config file.
            inputs[-1].name = "digit_bin"
            # Size is given as 1 regardless of the shape of the image.
            # This model does not support sending multiple files at once.
            inputs[-1].shape.append(1)
            # File name is needed by PIL to recognize extension.
            inputs[-1].parameters["file_name"].string_param = "image.png"
            # Body of the file is placed in bytes_content.
            inputs[-1].contents.bytes_contents.append(fp.read())

        request.inputs.extend(inputs)

        # Include name of the model in request.
        request.model_name = self.model_name

        try:
            response, _ = self.inference_stub.ModelInfer.with_call(request)
        except grpc.RpcError as rpc_error:
            print(f"ERROR: {rpc_error}")
            return rpc_error
        else:
            print(f"RECEIVED: {response}")

            # response.outputs[0]
            # The response may contain multiple outputs but MNIST YAML config has only one
            # so we can safely fetch output 0, the response.outputs[0].name will be `result`.

            # contents.int_contents
            # We expect the response to be a number so it will be placed in
            # contents.int_contents of output.

            # int_contents[0]
            # The response could possibly contain multiple integers but we expect only one
            # thus int_contents[0]

            return response.outputs[0].contents.int_contents[0]


if __name__ == "__main__":
    mnist_client = MnistClient("localhost", 8100)

    # Make sure the server is ready.
    if not mnist_client.send_server_ready_req():
        print("Server is not ready to accept requests.")

    # Make sure the model is ready.
    if not mnist_client.send_model_ready_req():
        print("Model is not ready to accept requests.")

    # Request inference.
    result_number = mnist_client.send_inference_req(
        "examples/grpc/mnist_client/test_images/8.png"
    )

    print(f"Recognized number: {result_number}")
