# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging

from ssf.application import SSFApplicationInterface
from ssf.results import *

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.samples = 0

    def build(self) -> int:
        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp startup")
        return RESULT_OK

    def request(self, params: list, meta: list) -> list:
        logger.info(f"MyApp request with params={params} meta={meta}")

        result = [
            {"requests": self.samples + idx, "x_times_1000": p["x"] * 1000}
            for idx, p in enumerate(params)
        ]
        self.samples = self.samples + len(result)

        logger.info(f"MyApp returning result={result}")
        return result

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK


# NOTE:
# This can be called multiple times (with separate processes)
# if running with multiple workers (replicas). Be careful that
# your application can handle multiple parallel worker processes.
# (for example, that there is no conflict for file I/O).
def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
