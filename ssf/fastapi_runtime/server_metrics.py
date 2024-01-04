# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import time
from typing import Sequence, Union

from fastapi import FastAPI
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from starlette.datastructures import MutableHeaders

from ssf.application_interface.runtime_settings import HEADER_METRICS_REQUEST_LATENCY
from ssf.common_runtime.metrics import (
    get_ssf_custom_metrics,
    get_default_custom_metrics,
)
from ssf.fastapi_runtime import server_health
from ssf.utils import API_FASTAPI


def add_prometheus_instrumentator(
    app: FastAPI,
    prometheus_port: str,
    prometheus_endpoint: str,
    prometheus_buckets: Sequence[Union[float, str]],
):

    metrics_endpoint = prometheus_endpoint
    if not metrics_endpoint.startswith("/"):
        metrics_endpoint = "/" + metrics_endpoint

    if prometheus_port:
        start_http_server(int(prometheus_port))

    # Prometheus instrumentator
    instrumentator = Instrumentator(
        excluded_handlers=[
            "/docs",
            "/openapi.json",
            metrics_endpoint,
            server_health.HEALTH_ROUTE_PREFIX + server_health.HEALTH_ROUTE_STARTUP,
            server_health.HEALTH_ROUTE_PREFIX + server_health.HEALTH_ROUTE_LIVE,
            server_health.HEALTH_ROUTE_PREFIX + server_health.HEALTH_ROUTE_READY,
        ]
    ).instrument(app)

    metrics = get_default_custom_metrics(
        prometheus_buckets, API_FASTAPI
    ) + get_ssf_custom_metrics(prometheus_buckets)
    [instrumentator.add(metric) for metric in metrics]

    if not prometheus_port:
        instrumentator.expose(app, endpoint=metrics_endpoint)


class RequestLatencyProviderMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):

        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        start_time = time.time()

        async def send_with_extra_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append(
                    HEADER_METRICS_REQUEST_LATENCY, str(time.time() - start_time)
                )
            await send(message)

        await self.app(scope, receive, send_with_extra_headers)
