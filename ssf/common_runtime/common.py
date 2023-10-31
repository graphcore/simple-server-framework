# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from pydantic import BaseModel
from typing_extensions import Final

# General header components.
HEADER_METRICS_REQUEST_LATENCY: Final[str] = "metrics-request-latency"
HEADER_METRICS_DISPATCH_LATENCY: Final[str] = "metrics-dispatch-latency"

# Prometheus
PROMETHEUS_BUCKETS = [
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1,
    1.5,
    2,
    2.5,
    3,
    3.5,
    4,
    4.5,
    5,
    7.5,
    10,
    30,
    60,
]
PROMETHEUS_ENDPOINT = "/metrics"

# Model describing schema for APIs that can throw HTTPExceptions.
class HTTPError(BaseModel):
    detail: str

    class Config:
        schema_extra = {
            "example": {"detail": "Reason for the HTTPException"},
        }
