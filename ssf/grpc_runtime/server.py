# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import logging
import os
from concurrent import futures
from multiprocessing import current_process
from threading import Thread

import grpc
from grpc_reflection.v1alpha import reflection

from ssf.common_runtime.callbacks import notify_error_callback

from ssf.common_runtime.config import settings

from ssf.common_runtime.dispatcher import Applications
from ssf.results import SSFExceptionArgumentsError

from ssf.utils import API_GRPC, ascii_to_object

from . import grpc_predict_v2_pb2, grpc_predict_v2_pb2_grpc
from .grpc_servicer import GRPCService

from ssf.common_runtime.metrics import (
    get_default_custom_metrics,
    get_ssf_custom_metrics,
)
from ssf.grpc_runtime.grpc_metrics import MetricsInterceptor
from prometheus_client import start_http_server


class AuthInterceptor(grpc.ServerInterceptor):
    def __init__(self, key):
        self._valid_metadata = ("rpc-auth-header", key)

        self._public_access_methods = [
            "/inference.GRPCInferenceService/ServerReady",
            "/inference.GRPCInferenceService/ServerLive",
        ]

        def deny(_, context):
            context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid key. Set valid `rpc-auth-header` request in metadata.",
            )

        self._deny = grpc.unary_unary_rpc_method_handler(deny)

    def intercept_service(self, continuation, handler_call_details):

        if handler_call_details.method in self._public_access_methods:
            return continuation(handler_call_details)

        metadata = handler_call_details.invocation_metadata
        metadata = metadata if metadata else ()

        for meta in metadata:
            if meta == self._valid_metadata:
                return continuation(handler_call_details)

        return self._deny


class gRPCserver:
    logger = logging.getLogger("ssf")

    def __init__(self, server_port, max_connections, api_key) -> None:
        self.ssf_config = ascii_to_object(os.getenv("SSF_CONFIG"))
        ssf_result_file = os.getenv("SSF_RESULT_FILE")
        settings.initialise(self.ssf_config, ssf_result_file)

        self.logger.info(f"> With settings {vars(settings)}")
        self.logger.debug(f"(From ssf_config {self.ssf_config})")

        self.application_id = self.ssf_config.application.id
        self.application_name = self.ssf_config.application.name
        self.application_desc = self.ssf_config.application.description
        self.application_version = self.ssf_config.application.version
        self.endpoints = self.ssf_config.endpoints

        self.server_port = server_port
        self.max_connections = max_connections
        self.api_key = api_key

        self.applications = Applications(
            settings=settings,
            ssf_config_list=[self.ssf_config],
            notify_error_callback=notify_error_callback,
        )

        self.startup_thread = None

    def run_applications(self):
        # Create the applications managed group.
        # A single application (=> single dispatcher) from our single ssf_config.
        self.logger.info("> Lifespan start")
        self.logger.info("Lifespan start : start application (threaded)")
        self.startup_thread = Thread(target=self.applications.start)
        self.startup_thread.start()

    def run_server(self):
        p_port = (
            int(settings.prometheus_port)
            if settings.prometheus_port
            else int(self.server_port) + 1
        )

        self.logger.info(f"> Loading {self.application_id} endpoint")

        interceptors = tuple()
        if self.api_key:
            self.logger.info(f"Running secure gRPC server with api key.")
            interceptors += (AuthInterceptor(self.api_key),)

        if not settings.prometheus_disabled:
            m_interceptor = MetricsInterceptor(
                [
                    "/inference.GRPCInferenceService/ServerReady",
                    "/inference.GRPCInferenceService/ServerLive",
                ],
                settings.prometheus_disabled,
            )

            if not settings.prometheus_disabled:
                [
                    m_interceptor.add(i)
                    for i in get_default_custom_metrics(
                        settings.prometheus_buckets, API_GRPC
                    )
                ]
                [
                    m_interceptor.add(i)
                    for i in get_ssf_custom_metrics(settings.prometheus_buckets)
                ]

            interceptors += (m_interceptor,)

            self.logger.debug(f"Prometheus metrics are served on port {p_port}")
            start_http_server(p_port)

        # currently in python gRPC max_workers defines just max concurrent connections
        # and not real server workers
        self.server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self.max_connections),
            interceptors=interceptors,
        )

        # For GRPC all endpoints will be generated in the same file
        grpc_predict_v2_pb2_grpc.add_GRPCInferenceServiceServicer_to_server(
            GRPCService(self.applications), self.server
        )
        SERVICE_NAMES = (
            grpc_predict_v2_pb2.DESCRIPTOR.services_by_name[
                "GRPCInferenceService"
            ].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(SERVICE_NAMES, self.server)
        self.server.add_insecure_port(f"[::]:{self.server_port}")
        self.server.start()
        self.logger.debug(
            f"> Start gRPC server (PID {current_process().pid}) (PORT {self.server_port})"
        )

    def run(self):
        self.logger.info(f"> Running gRPC server")
        self.logger.debug(f"settings={settings}")

        self.logger.info(f"> {self.application_name} : {self.application_desc}")
        self.logger.debug(f"ssf_config={self.ssf_config}")

        self.run_server()
        self.run_applications()

        try:
            self.server.wait_for_termination()
        except KeyboardInterrupt:
            self.logger.info(f"> gRPC server stopped by user")
            pass

        self.applications.stop()

        self.logger.info("> Lifespan stop")
        if self.startup_thread.is_alive():
            self.logger.info("Lifespan stop : joining startup thread")
            self.startup_thread.join()
            self.logger.info("Lifespan stop : stop application")
            self.applications.stop()
        else:
            self.logger.info("Lifespan stop : stop application")
            self.applications.stop()
