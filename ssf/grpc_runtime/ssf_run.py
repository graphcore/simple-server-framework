# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
from ssf.grpc_runtime.server import gRPCserver

import grpc

from ssf.results import SSFExceptionGRPCServerError, SSFExceptionArgumentsError

logger = logging.getLogger("ssf")


def run(args):
    app_dir = str(os.path.dirname(os.path.abspath(__file__)))
    logger.info(f"> Running gRPC service")

    if args.fastapi_replicate_server != 1:
        raise SSFExceptionArgumentsError(
            "Server replication is not supported when running gRPC server."
        )

    try:
        server = gRPCserver(args.port, args.grpc_max_connections, args.key)
        server.run()

    except grpc.RpcError as e:
        raise SSFExceptionGRPCServerError() from e
