# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging

from ssf.application_interface.application import SSFApplicationInterface
from ssf.application_interface.results import *

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp started")
        raise Exception("App startup failed")

    def request(self, params: dict, meta: dict) -> dict:
        logger.info("MyApp request")
        return {"result": "ok"}

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
