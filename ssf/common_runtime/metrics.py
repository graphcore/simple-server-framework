# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

from typing import Callable, Sequence, Union

from prometheus_fastapi_instrumentator import metrics
from prometheus_client import REGISTRY, Histogram
from prometheus_fastapi_instrumentator.metrics import Info, _is_duplicated_time_series

from ssf.common_runtime.common import HEADER_METRICS_DISPATCH_LATENCY
from ssf.results import SSFExceptionNotImplementedError
from ssf.utils import API_FASTAPI, API_GRPC


def get_default_custom_metrics(
    buckets: Sequence[Union[float, str]], api: str
) -> Sequence[Callable[[Info], None]]:
    if api == API_GRPC:
        prefix = "grpc"
    elif api == API_FASTAPI:
        prefix = "http"
    else:
        raise SSFExceptionNotImplementedError(f"Bad API string: {api}")

    return [
        metrics.latency(
            buckets=buckets,
            should_include_method=False,
            metric_name=f"{prefix}_request_duration_seconds",
            metric_doc="Duration of requests in seconds",
        ),
        metrics.request_size(
            should_include_method=False,
            metric_name=f"{prefix}_request_size_bytes",
        ),
        metrics.response_size(
            should_include_method=False,
            metric_name=f"{prefix}_response_size_bytes",
        ),
    ]


def get_ssf_custom_metrics(
    buckets: Sequence[Union[float, str]],
) -> Sequence[Callable[[Info], None]]:

    if buckets[-1] != float("inf"):
        buckets = [*buckets, float("inf")]

    label_names = ["handler", "status"]
    info_attribute_names = ["modified_handler", "modified_status"]

    try:

        DISPATCH_LATENCY_METRIC = Histogram(
            "ssf_dispatch_latency",
            "Duration of request limited to time spent in application.",
            labelnames=label_names,
            buckets=buckets,
            registry=REGISTRY,
        )

        def dispatch_latency_instrumentation(info: Info) -> None:

            label_values = [
                getattr(info, attribute_name) for attribute_name in info_attribute_names
            ]

            if HEADER_METRICS_DISPATCH_LATENCY in info.response.headers:
                observed_disp_latency = float(
                    info.response.headers[HEADER_METRICS_DISPATCH_LATENCY]
                )
                DISPATCH_LATENCY_METRIC.labels(*label_values).observe(
                    observed_disp_latency
                )

        return [dispatch_latency_instrumentation]
    except ValueError as e:
        if not _is_duplicated_time_series(e):
            raise e

    return None
