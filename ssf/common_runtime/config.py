# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from typing import Union
from ssf.common_runtime.common import PROMETHEUS_BUCKETS, PROMETHEUS_ENDPOINT


class Settings:
    # Complete set of arguments captured as a json string.
    ssf_args_json: str = None

    # Default to ssf_config.yaml in CWD.
    ssf_config_file: str = "ssf_config.yaml"

    # Default allow_origin_regex to use for CORS.
    allow_origin_regex: str = f"http.*://(?:localhost|127\.0\.0\.1)(?::\d+)?"

    # Default API key is None => do not secure.
    api_key: str = None
    api_key_timeout: int = 10080

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
        self.api_key = ssf_config.args.key
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
