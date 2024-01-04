# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

from locust_ssf_utils import testSSF
from locust import between, task


class ApplicationTests:
    # set also from Locust command line
    host = f"http://127.0.0.1:8100"
    # set delay from 0.2s to 0.5s after each request
    wait_time = between(0.1, 0.2)

    @task
    def test_v1_Test1_endpoint(self):
        self.client.post(
            "/v1/Test1",
            json={"x": 0.033},
            headers={"accept": "application/json", "Content-Type": "application/json"},
        )


testSSF(ApplicationTests, globals())
