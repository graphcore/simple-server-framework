# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from fastapi import APIRouter, status, Response

from ssf.application_interface.runtime_settings import settings
from ssf.common_runtime.dispatcher import Application
import logging

logger = logging.getLogger()

HEALTH_ROUTE_PREFIX = "/health"
HEALTH_ROUTE_STARTUP = "/startup"
HEALTH_ROUTE_READY = "/ready"
HEALTH_ROUTE_LIVE = "/live"

application: Application = None
router = APIRouter(prefix=HEALTH_ROUTE_PREFIX, tags=["Health"])


def initialize(app: Application):
    global application
    application = app
    logger.debug(f"router:Health Initialized with applications={application}")


# As soon as we start the server, the endpoints are ready to be read
@router.get(HEALTH_ROUTE_STARTUP, status_code=status.HTTP_200_OK)
def startup_check():
    return {"message": "Startup check succeeded."}


# The server readiness health check is meant to inform
# whether the server is ready to receive requests or not
@router.get(HEALTH_ROUTE_READY, status_code=status.HTTP_200_OK)
def readiness_check(response: Response):
    message = "Readiness check succeeded."
    if not application.is_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        message = "Readiness check failed."
    return {"message": message}


# The server liveness health check is meant to detect unrecoverable errors
# the server needs restart if unhealthy state is detected
@router.get(HEALTH_ROUTE_LIVE, status_code=status.HTTP_200_OK)
def liveness_check(response: Response):
    message = "Liveness check succeeded."
    if not application.is_alive():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        message = "Liveness check failed."
    return {"message": message}
