# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import time
from typing import Any, Callable
from urllib.parse import urlparse

import grpc
import grpc.experimental.gevent as grpc_gevent
from grpc_interceptor import ClientInterceptor
from locust import HttpUser, TaskSet, User, between, task

from ssf.grpc_runtime.test_utils_grpc import GRPCSession

# patch grpc so that it uses gevent instead of asyncio
grpc_gevent.init_gevent()


class LocustInterceptor(ClientInterceptor):
    def __init__(self, environment, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.env = environment

    def intercept(
        self,
        method: Callable,
        request_or_iterator: Any,
        call_details: grpc.ClientCallDetails,
    ):
        response = None
        exception = None
        start_perf_counter = time.perf_counter()
        response_length = 0
        try:
            response = method(request_or_iterator, call_details)
            response_length = response.result().ByteSize()
        except grpc.RpcError as e:
            exception = e

        self.env.events.request.fire(
            request_type="grpc",
            name=call_details.method,
            response_time=(time.perf_counter() - start_perf_counter) * 1000,
            response_length=response_length,
            response=response,
            context=None,
            exception=exception,
        )
        return response


class GrpcUser(User):
    abstract = True

    def __init__(self, environment):
        super().__init__(environment)

        service_ip, service_port = urlparse(self.host).netloc.split(":")
        self.client = GRPCSession(
            service_ip,
            int(service_port),
            intercept_channel=LocustInterceptor(environment=environment),
        )


def testSSF(TestClass, main_globals):
    main_globals[f"TestFastApi"] = type(
        "TestFastApi",
        (HttpUser,),
        dict(filter(lambda item: not item[0].startswith("_"), vars(TestClass).items())),
    )
    main_globals[f"TestGRPC"] = type(
        "TestGRPCApi",
        (GrpcUser,),
        dict(filter(lambda item: not item[0].startswith("_"), vars(TestClass).items())),
    )
