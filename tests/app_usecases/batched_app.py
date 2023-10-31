# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging

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
        logger.info("MyApp startup")
        return RESULT_OK

    def request(self, params_list: list, meta_list: list) -> list:
        result = []
        for idx, params in enumerate(params_list):
            meta = meta_list[idx]
            if meta["endpoint_id"] == "Test1":
                logger.info(f"MyApp request with params={params} meta={meta}")
                self.requests = self.requests + 1
                result.append({"requests": self.requests})
            if meta["endpoint_id"] == "Fail":
                if params["failure_type"] == "div0":
                    logger.info("MyApp request (Fail div0)")
                    x = 0 / 0
                elif params["failure_type"] == "malformed_result":
                    result.append([self.requests])
                else:
                    raise ValueError(f"Unknown failure type {params['failure_type']}")

        logger.info(f"MyApp returning result={result}")
        return result

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
