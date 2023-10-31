# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import requests

from ssf.application import SSFApplicationInterface, SSFConfig
from ssf.results import *

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self, ssf_config: SSFConfig):
        self.requests = 0
        logger.info(f"bash_cli : unknown_args={ssf_config.unknown_args}")
        logger.info(f"bash_cli : commands={ssf_config.args.commands}")

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
