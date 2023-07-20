# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import sys

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from contextlib import asynccontextmanager

from config import settings
from dispatcher import Applications
import server_security
import server_health
from ssf.fastapi_runtime.common import SSFException
from ssf.load_config import ConfigGenerator
from ssf.utils import load_module
from threading import Thread
import time
from ssf.logger import init_global_logging

init_global_logging()


logger = logging.getLogger()
logger.info(f"> Running FastAPI server")
logger.debug(f"settings={settings}")

# Load a single config file (=> single application endpoint).
ssf_config = ConfigGenerator(settings.ssf_config_file).load(api="fastapi")

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
applications = Applications(ssf_config_list=[ssf_config])
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
        logger.info("Lifespan applications.start()...")
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
        logger.info("Lifespan applications.stop()...")
        if startup_thread.is_alive():
            logger.warning("Startup thread still alive, joining...")
            time.sleep(2)
            applications.stop()
            startup_thread.join()
        else:
            applications.stop()
        logger.info("Lifespan applications.stop()...done")
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

app = FastAPI(
    lifespan=_lifespan,
    title=(application_name + (" (unsecure)" if settings.api_key is None else "")),
    description=application_desc,
    version=application_version,
    license_info=license_info,
    terms_of_service=application_terms_of_service,
    # contact
)

# TODO:
# What other middleware should we enable by default?
# e.g.:
#  Security
#  Health/readyness?
#
# app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com", "*.example.com"])
# app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
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
        raise SSFException(
            "FastAPI interface has not been prepared. Run SSF client `build` step first."
        )

    endpoint_module = load_module(endpoint_file, module_id)
    app.include_router(endpoint_module.router)

# Only include security module and endpoint when an API key has been specified.
if settings.api_key is None:
    logger.warning("API key has not been specified, endpoints are not secured.")
else:
    logger.info("> Adding security layer")
    app.include_router(server_security.router)

# Initialize and include server health router
server_health.initialize(applications)
app.include_router(server_health.router)


# Root end-point is always built-in.
@app.get("/")
async def home():
    return {"message": "OK"}
