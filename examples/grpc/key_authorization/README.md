# Overview
This example shows how to create a client, that is secured with an auth key, for the SSF server.
This client uses the example application defined in the SSF YAML file: `/examples/simple/ssf_config.yaml`

# Prerequisites
You must have SSF installed. Details on how to install it are given in [SSF Documentation](https://graphcore.github.io/simple-server-framework/docs/)
This example uses the basic `grpcio` Python library.

# Running
1. Start the SSF server (in this example the api key is `test_key`):
```bash
$ gc-ssf --config examples/simple/ssf_config.yaml --api grpc init build run --key "test_key"
```
2. Execute the client in a separate terminal:
```bash
$ python ssf_key_auth.py
```
