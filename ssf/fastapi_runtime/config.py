# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from ssf.logger import init_logging, set_default_logging_levels
from pydantic import BaseSettings
import os
import logging


class Settings(BaseSettings):

    root_pid: int = 0

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
    max_allowed_restarts: int = 3

    # Batching configuration.
    batching_timeout: float = 1

    # Look to .env in addition to local environment.
    class Config:
        env_file = ".env"


settings = Settings()

multiprocess = settings.root_pid != os.getpid()


def running_multiprocess():
    return multiprocess
