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
        logger.info("MyApp request")
        return {"result": "ok"}

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def is_healthy(self) -> bool:
        logger.info("MyApp check health")
        return True


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
