# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from fastapi import APIRouter, HTTPException, status, Response
from config import settings
from dispatcher import Applications
import logging

logger = logging.getLogger()

applications: Applications = None
router = APIRouter(prefix="/health", tags=["Health"])


def initialize(app: Applications):
    global applications
    applications = app
    logger.debug(f"router:Health Initialized with applications={applications}")


# As soon as we start the server, the endpoints are ready to be read
@router.get("/startup/", status_code=status.HTTP_200_OK)
def startup_check():
    return {"message": "Startup check succeeded."}


# The server readiness health check is meant to inform
# whether the server is ready to receive requests or not
@router.get("/ready/", status_code=status.HTTP_200_OK)
def readiness_check(response: Response):
    message = "Readiness check succeeded."
    if not applications.is_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        message = "Readiness check failed."
    return {"message": message}


# The server liveness health check is meant to detect unrecoverable errors
# the server needs restart if unhealthy state is detected
@router.get("/live/", status_code=status.HTTP_200_OK)
def liveness_check(response: Response):
    message = "Liveness check succeeded."
    if not applications.is_alive():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        message = "Liveness check failed."
    return {"message": message}
