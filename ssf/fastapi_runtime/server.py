# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import time
from contextlib import asynccontextmanager
from threading import Thread

import server_health
import server_security
import server_authentication
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ssf.common_runtime.callbacks import notify_error_callback

from ssf.application_interface.runtime_settings import settings

from ssf.common_runtime.dispatcher import Application
from ssf.application_interface.logger import init_global_logging, stop_global_logging

from ssf.fastapi_runtime.server_metrics import (
    RequestLatencyProviderMiddleware,
    add_prometheus_instrumentator,
)

from ssf.application_interface.results import SSFExceptionFrameworkResourceError
from ssf.utils import load_module, ascii_to_object

init_global_logging()

logger = logging.getLogger()
logger.info(f"> Running FastAPI server")

ssf_config = ascii_to_object(os.getenv("SSF_CONFIG"))
ssf_result_file = os.getenv("SSF_RESULT_FILE")
settings.initialise(ssf_config, ssf_result_file)

logger.info(f"> With settings {vars(settings)}")
logger.debug(f"(From ssf_config {ssf_config})")

application_id = ssf_config.application.id
application_name = ssf_config.application.name
application_desc = ssf_config.application.description
application_version = ssf_config.application.version

application_license_name = ssf_config.application.license_name
application_license_url = ssf_config.application.license_url
application_terms_of_service = ssf_config.application.terms_of_service

logger.info(f"> {application_name} : {application_desc}")
logger.debug(f"ssf_config={ssf_config}")


# Create the applications managed group.
# A single application (=> single dispatcher) from our single ssf_config.
logger.info(f"> Creating FastAPI applications")
applications = Application(
    settings=settings,
    ssf_config=ssf_config,
    notify_error_callback=notify_error_callback,
)
logger.debug(f"applications={applications}")


# TODO:
# How/where to handle stubbing (CLI, yaml and/or env config?)
# Add into the request metadata at run-time.


# Recent versions of FastAPI use a lifespan object to provide
# callbacks for start/stop events. The exception trapping is
# to workaround some ctrl-c exit behaviours - to make sure we
# can exit cleanly and call our registered application shutdowns.
# These manifest differently when running with --replicate > 1
# (multiple uvicorn workers) so be sure to test this too.
# TODO:
# Review these to see if/when they might be removed.
@asynccontextmanager
async def _lifespan(app: FastAPI):
    import asyncio

    try:
        logger.info("> Lifespan start")
        logger.info("Lifespan start : start application (threaded)")
        startup_thread = Thread(target=applications.start)
        startup_thread.start()
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass

    try:
        yield
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass

    try:
        logger.info("> Lifespan stop")
        if startup_thread.is_alive():
            time.sleep(2)
            logger.info("Lifespan stop : joining startup thread")
            startup_thread.join()
            logger.info("Lifespan stop : stop application")
            applications.stop()
        else:
            logger.info("Lifespan stop : stop application")
            applications.stop()
        stop_global_logging()
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass


logger.info(f"> Creating FastAPI instance")

license_info = None
if application_license_name is not None:
    license_info = {
        "name": application_license_name,
        "url": application_license_url,
    }

application_title = application_name
if settings.api_key is None and not settings.enable_session_authentication:
    application_title += " (unsecure)"

app = FastAPI(
    lifespan=_lifespan,
    title=application_title,
    description=application_desc,
    version=application_version,
    license_info=license_info,
    terms_of_service=application_terms_of_service,
    # contact
)

logger.info(
    f"Prometheus client is {'enabled' if not settings.prometheus_disabled else 'disabled'}."
)

# TODO:
# What other middleware should we enable by default?
# e.g.:
#  Security
#  Health/readyness?
#
# app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com", "*.example.com"])
# app.add_middleware(HTTPSRedirectMiddleware)

logger.info(
    f"CORS middleware is {'enabled' if settings.enable_cors_middleware else 'disabled'}."
)
if settings.enable_cors_middleware:
    logger.info(
        f"CORS middleware allow_origin_regex {settings.cors_allow_origin_regex}."
    )
    logger.info(f"CORS middleware allow_credentials {settings.cors_allow_credentials}.")
    logger.info(f"CORS middleware allow_methods {settings.cors_allow_methods}.")
    logger.info(f"CORS middleware allow_headers {settings.cors_allow_headers}.")
    logger.info(f"CORS middleware expose_headers {settings.cors_expose_headers}.")
    logger.info(f"CORS middleware max_age {settings.cors_max_age}.")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
        expose_headers=settings.cors_expose_headers,
        max_age=settings.cors_max_age,
    )

app.add_middleware(RequestLatencyProviderMiddleware)

# prometheus instrumentator should be added as last middleware
if not settings.prometheus_disabled:
    add_prometheus_instrumentator(
        app,
        settings.prometheus_port,
        settings.prometheus_endpoint,
        settings.prometheus_buckets,
    )

# Load the application endpoints
logger.info(f"> Loading endpoints for {application_id}")

for endpoint in ssf_config.endpoints:
    endpoint_file = endpoint.file
    module_id = f"{application_id}_endpoint_{endpoint.index}"
    logger.info(
        f"> Loading {application_id} endpoint from {endpoint_file} with module id {module_id}"
    )
    if not os.path.exists(endpoint_file):
        raise SSFExceptionFrameworkResourceError(
            f"Run `clean` and `build` steps to regenerate endpoint resources."
        )

    endpoint_module = load_module(endpoint_file, module_id)
    app.include_router(endpoint_module.router)

# Only include API key security module and endpoint when an API key has been specified.
if settings.api_key:
    logger.info("> Adding API key security layer")
    app.include_router(server_security.router)
else:
    logger.warning(
        "API key has not been specified, endpoints are not secured with API key."
    )

# Only include authentication module and endpoint when session authentication has been enabled.
if settings.enable_session_authentication:
    logger.info("> Adding authentication layer")
    app.include_router(server_authentication.router)
else:
    logger.warning(
        "Session authentication has not been specified, endpoints are not secured with authentication."
    )

# Initialize and include server health router
server_health.initialize(applications)
app.include_router(server_health.router)


# Root end-point is always built-in.
@app.get("/")
async def home():
    return {"message": "OK"}
