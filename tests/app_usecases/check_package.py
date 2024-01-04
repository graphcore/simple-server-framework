# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
from ssf.application_interface.application import SSFApplicationInterface
from ssf.application_interface.results import *
import google.protobuf as protobuf
import sys, os

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info(f"build import: {sys.modules['google.protobuf']}")
        logger.info(f"build executable: {sys.executable}")
        assert (
            protobuf.__version__ == "3.2.0"
        ), f"Wrong package version {protobuf.__version__}"
        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp startup")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        assert protobuf.__version__ == "3.2.0", "Wrong package version"
        return {"response": "ok"}

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK
