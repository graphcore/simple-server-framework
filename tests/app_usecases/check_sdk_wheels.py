# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
from ssf.application_interface.application import SSFApplicationInterface
from ssf.application_interface.results import *
import sys
import importlib

packages = [
    "poptorch",
    "poptorch_geometric",
    "tensorflow",
    "ipu_tensorflow_addons",
    "keras",
]
for p in packages:
    importlib.import_module(p)

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info(f"build executable: {sys.executable}")
        for p in packages:
            logger.info(f"Imported package {p} as {sys.modules[p]}")

        logger.info("MyApp build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp startup")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        return {"response": "ok"}

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK
