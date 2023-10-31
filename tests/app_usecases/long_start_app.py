# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import time
from ssf.application import SSFApplicationInterface
from ssf.results import *

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        time.sleep(5)
        logger.info("MyApp started")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        if meta["endpoint_id"] == "Test1":
            logger.info("MyApp request (Test1)")
            return {"response": "ok"}
        if meta["endpoint_id"] == "Fail":
            if params["failure_type"] == "div0":
                logger.info("MyApp request (Fail div0)")
                x = 0 / 0
            raise ValueError(f"Unknown failure type {params['failure_type']}")

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
