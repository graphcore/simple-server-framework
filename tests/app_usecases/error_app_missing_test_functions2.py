# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging

from ssf.application_interface.application import (
    SSFApplicationInterface,
    SSFApplicationTestInterface,
)
from ssf.application_interface.results import *

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp startup")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        if meta["endpoint_id"] == "Test1":
            logger.info(f"MyApp request with params={params} meta={meta}")
            self.requests = self.requests + 1
            result = {"requests": self.requests}
            logger.info(f"MyApp returning result={result}")
            return result

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK


class MyApplicationTest:
    def missing_begin(self, session, ipaddr: str) -> int:
        logger.info("MyApp test begin")
        return RESULT_OK

    def missing_subtest(self, session, ipaddr: str, index: int) -> (bool, str, bool):
        return (True, f"Dummy subtest", False)

    def missing_end(self, session, ipaddr: str) -> int:
        logger.info("MyApp test end")
        return RESULT_OK


def create_ssf_application_test_instance(ssf_config) -> SSFApplicationTestInterface:
    logger.info("Create MyApplication test instance")
    return MyApplicationTest()
