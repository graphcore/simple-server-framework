# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging

from ssf.application import SSFApplicationInterface

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info("MyApp build")
        return 0

    def startup(self) -> int:
        logger.info("MyApp startup")
        return 0

    def request(self, params: dict, meta: dict) -> dict:
        logger.info(f"MyApp request with params={params} meta={meta}")
        self.requests = self.requests + 1
        result = {"requests": self.requests, "x_times_1000": params["x"] * 1000}
        logger.info(f"MyApp returning result={result}")
        return result

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return 0

    def is_healthy(self) -> bool:
        logger.info("MyApp check health")
        return True


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
