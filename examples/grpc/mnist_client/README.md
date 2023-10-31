# Overview
This README describes an example SSF MNIST application client.
This client uses the model application that is defined in the SSF YAML file: `examples/models/mnist/mnist_config.yaml`

# Prerequisites
You must have SSF installed. Details on how to install it are given in [SSF Documentation](https://graphcore.github.io/simple-server-framework/docs/)
This example uses the basic `grpcio` Python library.

# Running
1. Start the SSF server:
```bash
$ gc-ssf --config examples/models/mnist/mnist_config.yaml --api grpc init build run
```
2. Execute the client in a separate terminal:
```bash
$ python ssf_mnist_client.py
```
