# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import requests
import os
from typing import Tuple

from ssf.application import SSFApplicationInterface, SSFApplicationTestInterface
from ssf.results import *
from ssf.utils import API_GRPC

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

    def process_sample(self, params):
        import numpy as np

        result = {}
        if "x_strings_list" in params:
            result["y_strings_list"] = params["x_strings_list"] + ["added on string"]

        if "x_ints_list" in params:
            result["y_ints_list"] = [i + 5 for i in params["x_ints_list"]]

        if "x_floats_list" in params:
            result["y_floats_list"] = (
                1.5 * np.array(params["x_floats_list"]) ** 2
            ).tolist()

        if "x_bools_list" in params:
            result["y_bools_list"] = [not i for i in params["x_bools_list"]]

        if "x_int_only" in params:
            result["y_int_only"] = params["x_int_only"] + 1

        if "x_bool_only" in params:
            result["y_bool_only"] = params["x_bool_only"]

        if "x_list_any" in params:
            result["y_list_any"] = params["x_list_any"] + [2]

        if "tempfile" in params:
            filename = params["tempfile"]

            try:
                with open(filename, "rb") as imgb:
                    imgbytes = imgb.read()
                result["out_image"] = imgbytes

            except Exception as e:
                logger.error(f"ERROR: Failed to load image {filename}. Reason:\n{e}")
                return result
        return result

    def request(self, params: dict, meta: dict) -> dict:
        logger.warning(f"MyApp request with params={params} meta={meta}")

        if isinstance(params, list):
            result = []
            for p in params:
                result.append(self.process_sample(p))
            return result

        return self.process_sample(params)

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        return RESULT_OK


# NOTE:
# This can be called multiple times (with separate processes)
# if running with multiple workers (replicas). Be careful that
# your application can handle multiple parallel worker processes.
# (for example, that there is no conflict for file I/O).
def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create MyApplication instance")
    return MyApplication()


class MyApplicationTest(SSFApplicationTestInterface):
    num_subtests = 5
    ssf_config = None

    def __init__(self, ssf_config) -> None:
        self.ssf_config = ssf_config
        super().__init__()

    def begin(self, session, ipaddr: str) -> int:
        logger.info("MyApp test begin")
        return RESULT_OK

    def submit_request(self, session, ipaddr: str, index: int, version: str):
        version = 1

        json_params = None
        gen_files = None
        gen_params = None

        test_input = None
        test_file_expected = None
        test_expected = None

        if index == 0:
            subtest_endp = "TestTypes"

            # Generic test input for text field
            test_input = {
                "x_strings_list": ["string", "red"],
                "x_ints_list": [0, 1, 2, 3, 4, 5],
                "x_floats_list": [0.5, 2.0, 4.0, 1.25],
                "x_bools_list": [True, False, True],
                "x_bool_only": True,
                "x_int_only": 5000,
            }
            if self.ssf_config.args.api != API_GRPC:
                test_input["x_list_any"] = ["string"]

            json_params = test_input

            # Expected test output for given input
            test_expected = {
                "y_strings_list": ["string", "red", "added on string"],
                "y_ints_list": [5, 6, 7, 8, 9, 10],
                "y_floats_list": [0.375, 6.0, 24.0, 2.34375],
                "y_bools_list": [False, True, False],
                "y_bool_only": True,
                "y_int_only": 5001,
            }
            if self.ssf_config.args.api != API_GRPC:
                test_expected["y_list_any"] = ["string", 2]

            logger.debug(
                f"MyApp types test index={index} test_input={test_input} test_expected={test_expected}"
            )

        elif index in range(1, self.num_subtests):
            subtest_endp = "TestFiles"

            # Specify and load binary image data
            input_image = f"test-image.png"

            test_file_input = {
                "tempfile": (
                    os.path.basename(input_image),
                    open(input_image, "rb"),
                    "image/png",
                )
            }

            with open(input_image, "rb") as fp:
                test_file_expected = fp.read()

            gen_files = test_file_input

            if index == 2:
                subtest_endp = "TestFilesWithSingleValueTypes"

                test_input = {
                    "x_bool_only": True,
                    "x_int_only": 5000,
                }

                test_expected = {
                    "y_bool_only": True,
                    "y_int_only": 5001,
                }

                gen_params = test_input

            elif index == 3:
                subtest_endp = "TestFilesWithListTypes"

                test_input = {
                    "x_strings_list": ["string", "red"],
                    "x_floats_list": [0.5, 2.0, 4.0, 1.25],
                }

                test_expected = {
                    "y_strings_list": ["string", "red", "added on string"],
                    "y_floats_list": [0.375, 6.0, 24.0, 2.34375],
                }

                gen_params = test_input

            elif index == 4:
                subtest_endp = "TestFilesWithMixtureOfTypes"

                test_input = {
                    "x_bool_only": True,
                    "x_int_only": 5000,
                    "x_strings_list": ["string", "red"],
                    "x_floats_list": [0.5, 2.0, 4.0, 1.25],
                }

                test_expected = {
                    "y_bool_only": True,
                    "y_int_only": 5001,
                    "y_strings_list": ["string", "red", "added on string"],
                    "y_floats_list": [0.375, 6.0, 24.0, 2.34375],
                }

                gen_params = test_input

        logger.debug(
            f"MyApp types test index={index} test_input={test_input} test_expected={test_expected} test_file_expected={test_file_expected[:100] if test_file_expected else None}"
        )

        # Send request
        url = f"{ipaddr}/v{version}/{subtest_endp}"

        response = session.post(
            url,
            params=gen_params,
            json=json_params,
            files=gen_files,
            headers={"accept": "*/*"},
            timeout=10,
        )

        logger.info(f"response=={response}")

        MAGIC1 = 200
        MAGIC2 = test_expected
        MAGIC3 = test_file_expected

        # General status code check
        ok_1 = response.status_code == MAGIC1
        if not ok_1:
            logger.error(
                f"Failed {url} with received={response.status_code} v expected={MAGIC1}"
            )
        else:
            logger.info(f"Types test {index}: ok_1 passed.")

        # Types subtest output check - for tests with image this checks the headers strings
        ok_2 = True  # in case no data expected in output
        if index == 0:
            ok_2 = response.json() == test_expected

        if index in range(2, self.num_subtests):
            headers = response.headers
            MAGIC2 = {i: f"{MAGIC2[i]}" for i in MAGIC2}
            for k in MAGIC2:
                try:
                    ok_2 = MAGIC2[k] == headers[k]
                    if not ok_2:
                        break
                except Exception as e:
                    logger.error(f"Types subtest {index} error: {e}")
                    ok_2 = False
                    break

        if not ok_2:
            logger.error(
                f"Failed {url} inputs={test_input} with received={response.json()} v expected={MAGIC2}"
            )
        else:
            logger.info(f"Types test {index}: ok_2 passed.")

        # Image subtest output check - index 1->4 contain an image output
        ok_3 = True  # in case no image expected in output
        if index in range(1, self.num_subtests):
            # files subtest output check
            ok_3 = response.content == MAGIC3

            if not ok_3:
                logger.error(
                    f"Failed {url} with {input_image} : {response.content[:100]}... v expected {MAGIC2[:100]}..."
                )
            else:
                logger.info(f"Types test {index}: ok_3 passed.")

        return response, subtest_endp, test_input, ok_1, ok_2, ok_3

    def subtest(self, session, ipaddr: str, index: int) -> Tuple[bool, str, bool]:
        logger.info(f"STARTING TEST {index+1}")

        version = "1"
        last_index = self.num_subtests - 1

        try:
            _, subtest_endp, test_input, ok_1, ok_2, ok_3 = self.submit_request(
                session, ipaddr, index, version
            )

            return (
                ok_1 == ok_2 == ok_3 == True,
                f"v{version}-{subtest_endp} {test_input} results: status = {ok_1}, params = {ok_2}.",
                index < last_index,
            )

        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return (False, e, False)

    def end(self, session, ipaddr: str) -> int:
        logger.info("MyApp test end")
        return RESULT_OK


def create_ssf_application_test_instance(ssf_config) -> SSFApplicationTestInterface:
    logger.info("Create MyApplication test instance")
    return MyApplicationTest(ssf_config)
