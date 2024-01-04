# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from http import HTTPStatus

import pytest
import re
import requests
from ssf.application_interface.runtime_settings import HEADER_METRICS_REQUEST_LATENCY

from ssf.grpc_runtime.test_utils_grpc import GRPCSession
from ssf.utils import API_GRPC
import utils

from pytest import server_port


class PrometheusConfig(utils.TestClient):
    def configure(
        self, disable=False, custom_port=None, custom_endpoint=None, custom_buckets=None
    ):
        if not getattr(self, "extra_arguments", None):
            self.extra_arguments = []

        if disable:
            self.extra_arguments.extend(["--prometheus-disabled"])

        if custom_endpoint:
            self.extra_arguments.extend(["--prometheus-endpoint", custom_endpoint])

        if custom_port:
            self.extra_arguments.extend(["--prometheus-port", custom_port])

        if custom_buckets:
            self.extra_arguments = ["--prometheus-buckets"] + custom_buckets

        if self.api == API_GRPC:
            prometheus_port = custom_port if custom_port else int(server_port) + 1
            self.m_prefix = "grpc"
            self.m_OK_stat = "OK"
        else:
            prometheus_port = custom_port if custom_port else int(server_port)
            self.metrics_url = self.base_url
            self.m_prefix = "http"
            self.m_OK_stat = "2xx"

        self.metrics_default_address = (
            f"http://{self.base_host}:{prometheus_port}/metrics"
        )

        if custom_endpoint:
            self.metrics_custom_address = (
                f"http://{self.base_host}:{prometheus_port}/{custom_endpoint}"
            )
        else:
            # to make sure it crashes when used unintentionally
            self.metrics_custom_address = None

    def send_infer_request(self, request_json, application, endpoint, version):
        """Sends inference reqest to server and verifies result

        Args:
            request_json (dict): dictionary with sent parameters i.e. {"x": 0}
            application (str): Application name
            endpoint (str): Endpoint name
            version (str): Endpoint version

        Returns:
            handler : str, response : request.Response | ModelInferResponse:
                string `handler` that identifies the requet in metrics
                and `response` appropriate to server api type
        """
        if self.api == API_GRPC:
            try:
                response = self.grpc_session.grpc_send_infer_request(
                    version, endpoint, request_json
                )
            except Exception as e:
                assert False, "Failed to communicate with gRPC server."
            m_handler = f"ModelInfer/{application}/v{version}/{endpoint}"
        else:
            url = f"{self.base_url}/v{version}/{endpoint}"
            response = requests.post(
                url,
                json=request_json,
                headers={"accept": "application/json"},
                timeout=1,
            )
            assert response.status_code == 200
            m_handler = f"/v{version}/{endpoint}"

        return m_handler, response


@pytest.mark.fast
class TestPrometheusEnabled(PrometheusConfig):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        super().configure(self)

    def test_metrics_client_starts(self):
        """Metrics clients starts, is responsive and updates"""
        response = requests.get(self.metrics_default_address)
        # no request has been made yet so no metrics has been exported
        assert not "/v1/Test1" in response.text

        m_handler, _ = self.send_infer_request({"x": 0}, "simple-test", "Test1", "1")

        response = requests.get(self.metrics_default_address)

        # counter incremented to 1
        assert (
            f'ssf_dispatch_latency_count{{handler="{m_handler}",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )
        assert (
            f'{self.m_prefix}_request_duration_seconds_count{{handler="{m_handler}",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )
        assert (
            f'{self.m_prefix}_request_duration_seconds_bucket{{handler="{m_handler}",le="+Inf",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )
        assert (
            f'{self.m_prefix}_request_size_bytes_count{{handler="{m_handler}",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )
        assert (
            f'{self.m_prefix}_response_size_bytes_count{{handler="{m_handler}",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )


@pytest.mark.fast
class TestPrometheusDisabled(PrometheusConfig):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        super().configure(self, disable=True)

    def test_metrics_client_disabled(self):
        """Metrics clients can be disabled"""
        try:
            response = requests.get(self.metrics_default_address, timeout=1)
            # no request has been made yet so no metrics has been exported
            assert response.status_code == HTTPStatus.NOT_FOUND
        except Exception as e:
            # This server does not exist
            assert "Connection refused" in str(e)


@pytest.mark.fast
class TestPrometheusCustomEndpoint(PrometheusConfig):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        super().configure(self, custom_endpoint="metrics_test")

    def test_metrics_client_custom_endpoint(self):
        """User can set custom metrics endpoint address"""

        response = requests.get(self.metrics_default_address, timeout=1)

        if self.api == API_GRPC:
            # for GRPc metrics will always be server on all endpoints
            assert response.status_code == HTTPStatus.OK
        else:
            assert response.status_code == HTTPStatus.NOT_FOUND

        print(f"HUEBRT {self.metrics_custom_address}")
        response = requests.get(self.metrics_custom_address, timeout=1)
        assert response.status_code == HTTPStatus.OK


@pytest.mark.fast
class TestPrometheusCustomPort(PrometheusConfig):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        super().configure(self, custom_port="8183")

    def test_metrics_client_custom_port(self):
        """User can set metrics to run on custom port"""

        m_handler, _ = self.send_infer_request({"x": 0}, "simple-test", "Test1", "1")

        response = requests.get(self.metrics_default_address, timeout=1)
        # counter incremented to 1
        assert (
            f'ssf_dispatch_latency_count{{handler="{m_handler}",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )
        assert (
            f'{self.m_prefix}_request_duration_seconds_count{{handler="{m_handler}",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )
        assert (
            f'{self.m_prefix}_request_duration_seconds_bucket{{handler="{m_handler}",le="+Inf",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )
        assert (
            f'{self.m_prefix}_request_size_bytes_count{{handler="{m_handler}",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )
        assert (
            f'{self.m_prefix}_response_size_bytes_count{{handler="{m_handler}",status="{self.m_OK_stat}"}} 1.0'
            in response.text
        )


@pytest.mark.fast
class TestPrometheusCustomBuckets(PrometheusConfig):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        self.custom_buckets = ["0.75", "1.5"]
        super().configure(self, custom_buckets=self.custom_buckets)

    def test_metrics_client_custom_buckets(self):
        """User can set custom bucket thresholds"""

        self.send_infer_request({"x": 0}, "simple-test", "Test1", "1")

        response = requests.get(self.metrics_default_address, timeout=1)
        search_result = re.findall('le="([0-9.]*)"', response.text)

        search_result_check = [t in search_result for t in self.custom_buckets]
        search_result_filtered = [
            e for e in search_result if e not in self.custom_buckets
        ]

        assert all(
            search_result_check
        ), f"Not all buckets were used {self.custom_buckets}"

        assert not search_result_filtered, "Undesired buckets were exposed."


@pytest.mark.fast
class TestSSFLatencyMetrics(PrometheusConfig):
    """Test that ssf_request_latency is present when Prometheus is disabled"""

    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        super().configure(self, disable=True)

    def test_sff_latency_present(self):
        """User can set custom bucket thresholds"""

        _, response = self.send_infer_request({"x": 0}, "simple-test", "Test1", "1")

        if self.api == API_GRPC:
            assert response.parameters[
                HEADER_METRICS_REQUEST_LATENCY
            ], f"{HEADER_METRICS_REQUEST_LATENCY} not in parameters"
        else:
            assert response.status_code == 200
            assert response.headers[
                HEADER_METRICS_REQUEST_LATENCY
            ], f"{HEADER_METRICS_REQUEST_LATENCY} not in headers"


test_grpc = [
    TestPrometheusEnabled,
    TestPrometheusDisabled,
    TestPrometheusCustomEndpoint,
    TestPrometheusCustomPort,
    TestPrometheusCustomBuckets,
    TestSSFLatencyMetrics,
]

for c in test_grpc:
    globals()[f"{c.__name__}GRPC"] = utils.withGRPC(c)
