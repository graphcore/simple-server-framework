# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import time
import requests

from ssf.application import (
    SSFApplicationInterface,
    SSFApplicationTestInterface,
    SSFConfig,
)
from ssf.results import *

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self, ssf_config: SSFConfig):
        id = ssf_config.config_dict["application"]["id"]
        version = ssf_config.config_dict["application"]["version"]
        logger.info(f"MyApp {id} {version}")
        self.requests = 0

    def build(self) -> int:
        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp startup")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        self.requests = self.requests + 1
        time.sleep(float(params["x"]))
        return {"requests": self.requests}

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK
