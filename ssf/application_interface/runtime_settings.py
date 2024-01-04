# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# NOTE:
# Do not import external packages in application_interface modules
# to avoid introducing additional dependencies for the application.
# Only import SSF modules that are also in application_interface.

from typing import Union, List
import sys

if sys.version_info >= (3, 8, 0):
    from typing import Final
else:
    from typing import Generic, TypeVar

    class Final(Generic[TypeVar("T", bound=str)]):
        pass


# General header components.
HEADER_METRICS_REQUEST_LATENCY: Final[str] = "metrics-request-latency"
HEADER_METRICS_DISPATCH_LATENCY: Final[str] = "metrics-dispatch-latency"

# Prometheus
PROMETHEUS_BUCKETS = [
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1,
    1.5,
    2,
    2.5,
    3,
    3.5,
    4,
    4.5,
    5,
    7.5,
    10,
    30,
    60,
]
PROMETHEUS_ENDPOINT = "/metrics"


class Settings:
    # Complete set of arguments captured as a json string.
    ssf_args_json: str = None

    # Default to ssf_config.yaml in CWD.
    ssf_config_file: str = "ssf_config.yaml"

    # FastAPI CORS middleware configuration.
    enable_cors_middleware = False
    cors_allow_origin_regex: str = None
    cors_allow_credentials: bool = None
    allow_methods: List[str] = None
    allow_headers: List[str] = None
    expose_headers: List[str] = None
    max_age: int = None

    # Default API key is None => do not secure.
    api_key: str = None
    api_key_timeout: int = 10080

    # Session authentication
    enable_session_authentication: bool = False
    session_authentication_timeout: int = 10080
    session_authentication_module_file: str = None

    # Logging levels.
    file_log_level: str = "INFO"
    stdout_log_level: str = "INFO"

    # Number of application replicas.
    replicate_application: int = 1

    # Watchdog settings.
    watchdog_request_threshold: float = 0
    watchdog_request_average: int = 3
    watchdog_ready_period: int = 5
    max_allowed_restarts: int = 3
    stop_on_error: bool = False

    # Batching configuration.
    batching_timeout: float = 1

    # Modifications to config.
    modify_config: str = None

    # Result file for server exit code.
    result_file: str = None

    # Prometheus metrics
    prometheus_disabled: bool = False
    prometheus_buckets: list = PROMETHEUS_BUCKETS
    prometheus_endpoint: str = PROMETHEUS_ENDPOINT
    prometheus_port: Union[str, None]

    def initialise(self, ssf_config, ssf_result_file):
        self.ssf_config_file = ssf_config.config_file
        self.enable_cors_middleware = ssf_config.args.enable_cors_middleware
        self.cors_allow_origin_regex = ssf_config.args.cors_allow_origin_regex
        self.cors_allow_credentials = ssf_config.args.cors_allow_credentials
        self.cors_allow_methods = ssf_config.args.cors_allow_methods.split(",")
        self.cors_allow_headers = ssf_config.args.cors_allow_headers.split(",")
        self.cors_expose_headers = ssf_config.args.cors_expose_headers.split(",")
        self.cors_max_age = ssf_config.args.cors_max_age
        self.api_key = ssf_config.args.key
        self.enable_session_authentication = (
            ssf_config.args.enable_session_authentication
        )
        self.session_authentication_timeout = (
            ssf_config.args.session_authentication_timeout
        )
        self.session_authentication_module_file = (
            ssf_config.args.session_authentication_module_file
        )
        self.file_log_level = ssf_config.args.file_log_level
        self.stdout_log_level = ssf_config.args.stdout_log_level
        self.replicate_application = ssf_config.args.replicate_application
        self.watchdog_request_threshold = ssf_config.args.watchdog_request_threshold
        self.watchdog_request_average = ssf_config.args.watchdog_request_average
        self.watchdog_ready_period = ssf_config.args.watchdog_ready_period
        self.max_allowed_restarts = ssf_config.args.max_allowed_restarts
        self.stop_on_error = ssf_config.args.stop_on_error
        self.batching_timeout = ssf_config.args.batching_timeout
        self.modify_config = ssf_config.args.modify_config
        self.prometheus_disabled = ssf_config.args.prometheus_disabled
        self.prometheus_buckets = ssf_config.args.prometheus_buckets
        self.prometheus_endpoint = ssf_config.args.prometheus_endpoint
        self.prometheus_port = ssf_config.args.prometheus_port
        self.result_file = ssf_result_file


settings: Settings = Settings()
