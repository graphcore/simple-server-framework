# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
from ssf.application_interface.application import SSFApplicationInterface
from ssf.application_interface.results import *
import yaml

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
        result = {"response": "ok"}
        logger.info(f"MyApp returning result={result}")
        return result

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        file = open("status.yaml", "r")
        healthy = yaml.safe_load(file)["healthy"]
        ret = RESULT_OK if healthy else RESULT_APPLICATION_ERROR
        logger.info(f"MyApp returning {ret} from watchdog()")
        return ret


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()
