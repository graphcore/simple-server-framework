<!-- Copyright (c) 2023 Graphcore Ltd. All rights reserved. -->
# Simple Server Framework - gRPC Runtime

## Overview

Support for a gRPC framework has been implemented using the grpcio Python module. SSF servers supports reflection so the gRPC framework can be discovered using clients that support reflection. The gRPC runtime is based on [Predict Protocol - Version 2 proposed by KServe](https://kserve.github.io/website/0.8/modelserving/inference_api/). Predict Protocol support is limited to the data types that are supported in SSF.

## Files

- `grpc_common.py` : Common code for gRPC implementation
- `grpc_predict_v2_pb2_grpc.py` `grpc_predict_v2_pb2.py` `grpc_predict_v2_pb2.pyi` :  gRPC protocol files generated using grpc_tools
- `grpc_servicier.py` : Python gRPC implementation of defied gRPC interface
- `grpc_types.py` : Definitions of SSF types for gRPC
- `server.py` : Main server app
- `ssf_run.py` : Entry point (starts GRPC server)

## Regenerating grpc_tools files

Proto file for generating gRPC interface is available along with KServe source. Following command run from main directory of the project can be used to regenerate gRCP interface files:

```bash
python3 -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. --pyi_out=.  ssf/grpc_runtime/*.proto
```

## Testing gRPC

For quick testing, any client that supports reflection can be used. Rapid option is grpcui which can be started from DockerHub. Exemplary command line to start gRPC client UI on port 8080:

```bash
docker run --init --rm -p 8080:8080 --network=host fullstorydev/grpcui -max-msg-sz 10063522 -plaintext 0.0.0.0:8100
```

## Environment variables

These variables are set automatically by SSF when `ssf run` is issued (see `ssf_run.py`):

- `SSF_CONFIG_FILE` : The config file to run.
- `FILE_LOG_LEVEL` : Set log level for file log
- `STDOUT_LOG_LEVEL` : Set the log level for stdout
- `WATCHDOG_REQUEST_THRESHOLD` : Request duration watchdog threshold
- `WATCHDOG_REQUEST_AVERAGE` : Number of last requests factored in request duration watchdog
- `BATCHING_TIMEOUT` : Timeout in seconds the server waits to accumulate samples if batching is enabled
