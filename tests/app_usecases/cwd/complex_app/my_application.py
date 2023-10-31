# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import requests

from ssf.application import SSFApplicationInterface, SSFApplicationTestInterface
from ssf.results import *

# description from config directory.
from description import *

# builder from application module directory.
from builder import *

# core from directory relative to custom syspath.
from core import *

logger = logging.getLogger()

# Confirm 'description' module is imported.
print(DESCRIPTION)


class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.requests = 0

    def build(self) -> int:
        logger.info(f"MyApp build CWD:{os.getcwd()}")

        # Confirm 'builder' module is imported and available.
        builder()

        return RESULT_OK

    def startup(self) -> int:
        logger.info(f"MyApp startup CWD:{os.getcwd()}")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        logger.info(f"MyApp request CWD:{os.getcwd()} with params={params} meta={meta}")
        self.requests = self.requests + 1
        result = {"requests": self.requests}
        return result

    def shutdown(self) -> int:
        logger.info(f"MyApp shutdown CWD:{os.getcwd()}")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info(f"MyApp watchdog CWD:{os.getcwd()}")
        return RESULT_OK


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info(f"MyApp create_ssf_application_instance CWD:{os.getcwd()}")
    return MyApplication()


class MyApplicationTest(SSFApplicationTestInterface):
    def begin(self, session, ipaddr: str) -> int:
        logger.info(f"MyApp test begin CWD:{os.getcwd()}")
        return 0

    def subtest(self, session, ipaddr: str, index: int) -> (bool, str, bool):
        logger.info(f"MyApp test subtest CWD:{os.getcwd()}")

        # Confirm 'core' module is imported and available.
        core()

        try:
            url = f"{ipaddr}/v1/Test1"
            params = {"x": 0}
            response = session.post(
                url, json=params, headers={"accept": "application/json"}, timeout=5
            )

            MAGIC1 = 200
            MAGIC2 = f'{{"requests":{index+1}}}'
            ok = response.status_code == MAGIC1 and response.text == MAGIC2

            if not ok:
                logger.error(
                    f"Failed {url} with {params} : {response.status_code}/{response.text} v expected {MAGIC1}/{MAGIC2}"
                )

            return (ok, "", False)

        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return (False, e, False)

    def end(self, session, ipaddr: str) -> int:
        logger.info(f"MyApp test end CWD:{os.getcwd()}")
        return 0


def create_ssf_application_test_instance(ssf_config) -> SSFApplicationTestInterface:
    logger.info(f"MyApp create_ssf_application_test_instance CWD:{os.getcwd()}")
    return MyApplicationTest()
