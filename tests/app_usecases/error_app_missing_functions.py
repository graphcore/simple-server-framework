# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging

from ssf.application_interface.application import SSFApplicationInterface
from ssf.application_interface.results import *

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def missing_build(self) -> int:
        logger.info("MyApp build")
        return RESULT_OK

    def missing_startup(self) -> int:
        logger.info("MyApp startup")
        return RESULT_OK

    def missing_request(self, params: dict, meta: dict) -> dict:
        if meta["endpoint_id"] == "Test1":
            logger.info(f"MyApp request with params={params} meta={meta}")
            self.requests = self.requests + 1
            result = {"requests": self.requests}
            logger.info(f"MyApp returning result={result}")
            return result

    def missing_shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def missing_watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
