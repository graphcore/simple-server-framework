# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import concurrent
import logging
from dataclasses import dataclass
from time import sleep
from typing import Tuple

from ssf.application import SSFApplicationInterface, SSFApplicationTestInterface
from ssf.common_runtime.common import (
    HEADER_METRICS_DISPATCH_LATENCY,
    HEADER_METRICS_REQUEST_LATENCY,
)
from ssf.results import *

from my_application import MyApplication, MyApplicationTest

logger = logging.getLogger()


class ApplicationTest(MyApplicationTest):
    def task_with_delay(self, delay_in_seconds, func, *argv):
        sleep(delay_in_seconds)
        return func(*argv)

    def err(self, test_desc, fail_reason, debug_info):
        logger.error(f"{test_desc} {fail_reason} {debug_info}")
        return f"batching test: {test_desc} FAILED. Reason: {fail_reason}"

    def subtest(self, session, ipaddr: str, index: int) -> Tuple[bool, str, bool]:
        batch_size = self.ssf_config.application.max_batch_size
        batching_timeout = self.ssf_config.args.batching_timeout

        assert (batch_size < self.num_subtests, "Test broken")
        assert (batch_size == 4, "Test broken")

        # test config:
        #   test description,
        #   number of clients,
        #   expected max request latencies - count of requests that will be
        #       processed with time greater than batching requests
        #   expected internal batches - count of batches that will be sent
        #       separately to application
        #   sleep pattern - index of requests that will be delayed to next batch
        tests = [
            # request waits whole batching time
            ["one sample", 1, 1, 1, []],
            # all requests processed immediately - batch is full right away
            ["one batch", batch_size, 0, 1, []],
            ["two batches", 2 * batch_size, 0, 2, []],
            # all requests wait - batch is never full
            ["incomplete batch", batch_size - 1, batch_size - 1, 1, []],
            # over batch requests wait
            ["over batch", batch_size + 1, 1, 2, []],
            ["over two batches", 2 * batch_size + 1, 1, 3, []],
            # unbalanced load - hold in the middle of full batch
            [
                "hold in the middle of full batch",
                batch_size,
                batch_size,
                2,
                [batch_size / 2],
            ],
        ]

        continue_test = index + 1 < len(tests)

        (
            test_desc,
            num_of_clients,
            exp_max_latencies,
            exp_batches_count,
            sleep_pattern,
        ) = tests[index]
        logger.info(f"STARTING TEST {index} : {test_desc}")

        version = "1"

        request_latencies = []
        # collecting just unique values to count number of separate application executions
        dispatch_latencies = set()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []

            for idx in range(num_of_clients):
                # calling different types test from base class to cover more cases
                # num_subtests - number of base class tests
                submit_request_args = (
                    session,
                    ipaddr,
                    idx % self.num_subtests,
                    version,
                )
                if idx in sleep_pattern:
                    futures.append(
                        executor.submit(
                            self.task_with_delay,
                            batching_timeout * 1.5,
                            self.submit_request,
                            *submit_request_args,
                        )
                    )
                else:
                    futures.append(
                        executor.submit(self.submit_request, *submit_request_args)
                    )

            for future in concurrent.futures.as_completed(futures):
                response, _, _, ok_1, ok_2, ok_3 = future.result()

                # check response validity
                if not all((ok_1, ok_2, ok_3)):
                    return (
                        False,
                        self.err(test_desc, "response not valid", (ok_1, ok_2, ok_3)),
                        continue_test,
                    )

                request_latencies.append(
                    float(response.headers[HEADER_METRICS_REQUEST_LATENCY])
                )
                dispatch_latencies.add(
                    float(response.headers[HEADER_METRICS_DISPATCH_LATENCY])
                )

            # check if the batching time was correct
            max_request_latencies = [
                l for l in request_latencies if l > batching_timeout
            ]

            if len(max_request_latencies) != exp_max_latencies:
                return (
                    False,
                    self.err(
                        test_desc,
                        "unexpected request latencies values",
                        request_latencies,
                    ),
                    continue_test,
                )

            if len(dispatch_latencies) != exp_batches_count:
                return (
                    False,
                    self.err(
                        test_desc,
                        "unexpected dispatch latencies values",
                        dispatch_latencies,
                    ),
                    continue_test,
                )

        return (True, f"batching test: {test_desc} - SUCCESS", continue_test)


def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info(f"Create {MyApplication.__name__} instance")
    return MyApplication()


def create_ssf_application_test_instance(ssf_config) -> SSFApplicationTestInterface:
    logger.info(f"Create {ApplicationTest.__name__} test instance")
    return ApplicationTest(ssf_config)
