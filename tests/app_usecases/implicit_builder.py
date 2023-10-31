# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import requests
from ssf.application import SSFApplicationInterface, SSFApplicationTestInterface
from ssf.results import *

logger = logging.getLogger()


class AnyParent:
    pass


class MyApplication(AnyParent, SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp startup")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        logger.info(f"MyApp request with params={params} meta={meta}")
        self.requests = self.requests + 1
        result = {"requests": self.requests, "x_times_1000": params["x"] * 1000}
        logger.info(f"MyApp returning result={result}")
        return result

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK


class MyApplicationTest(SSFApplicationTestInterface):
    def begin(self, session, ipaddr: str) -> int:
        logger.info("MyApp test begin")
        return RESULT_OK

    def subtest(self, session, ipaddr: str, index: int) -> (bool, str, bool):
        return (
            True,
            "ok",
            False,
        )

    def end(self, session, ipaddr: str) -> int:
        logger.info("MyApp test end")
        return RESULT_OK
