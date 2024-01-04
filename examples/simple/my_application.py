# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import requests

from ssf.application_interface.application import (
    SSFApplicationInterface,
    SSFApplicationTestInterface,
)
from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import *

logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def __init__(self, ssf_config: SSFConfig):
        id = ssf_config.config_dict["application"]["id"]
        version = ssf_config.config_dict["application"]["version"]
        logger.info(f"MyApp {id} {version}")
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
        return 0

    def subtest(self, session, ipaddr: str, index: int) -> (bool, str, bool):

        vers = 2
        subs_per_ver = 10
        total = vers * subs_per_ver
        ver = int(index / subs_per_ver) + 1
        ver_sub = index % subs_per_ver

        test_input = ver_sub ** 3
        test_expected = test_input * 1000

        logger.debug(
            f"MyApp test index={index}/{total} ver={ver} sub={ver_sub}/{subs_per_ver} test_input={test_input} test_expected={test_expected}"
        )

        try:
            url = f"{ipaddr}/v{ver}/Test1"
            params = {"x": test_input}
            response = session.post(
                url, json=params, headers={"accept": "application/json"}, timeout=5
            )

            MAGIC1 = 200
            MAGIC2 = f'{{"requests":{index+1},"x_times_1000":{test_expected}}}'
            ok = response.status_code == MAGIC1 and response.text == MAGIC2

            if not ok:
                logger.error(
                    f"Failed {url} with {params} : {response.status_code}/{response.text} v expected {MAGIC1}/{MAGIC2}"
                )

            return (
                ok,
                f"v{ver} {ver_sub} {test_input}x1000=={test_expected}",
                index < total - 1,
            )

        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return (False, e, False)

    def end(self, session, ipaddr: str) -> int:
        logger.info("MyApp test end")
        return 0
