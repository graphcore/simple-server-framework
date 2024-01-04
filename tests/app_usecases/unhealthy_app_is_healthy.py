# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import yaml

from ssf.application_interface.application import SSFApplicationInterface
from ssf.application_interface.results import *

logger = logging.getLogger()

# This tests:
# - The old is_healthy() watchdog name still works.
# - Even if we don't derive from SSFApplicationInterface.
class MyApplication:
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp startup")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        result = {"response": "ok"}
        logger.info(f"MyApp returning result={result}")
        return result

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def is_healthy(self) -> bool:
        logger.info("MyApp health check")
        file = open("status.yaml", "r")
        healthy = yaml.safe_load(file)["healthy"]
        ret = True if healthy else False
        logger.info(f"MyApp returning {ret} from is_healthy()")
        return ret


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
