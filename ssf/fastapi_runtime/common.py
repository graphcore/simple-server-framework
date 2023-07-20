# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from typing_extensions import Final
from pydantic import BaseModel

# General header components.
HEADER_METRICS_REQUEST_LATENCY: Final[str] = "metrics-request-latency"
HEADER_METRICS_DISPATCH_LATENCY: Final[str] = "metrics-dispatch-latency"

# Model describing schema for APIs that can throw HTTPExceptions.
class HTTPError(BaseModel):
    detail: str

    class Config:
        schema_extra = {
            "example": {"detail": "Reason for the HTTPException"},
        }


class SSFException(Exception):
    """Exception for unrecoverable problems which should be
    presented to the user as a meaningful error message.
    """
