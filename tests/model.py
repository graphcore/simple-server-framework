# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# import os
from abc import ABC, abstractmethod
import logging
import os
import pytest
import sys

from utils import run_subprocess
import ssf.docker as docker
from ssf.results import *


def get_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("TEST MODEL: %(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


class TestModel(ABC):
    @classmethod
    def setup_class(cls):
        cls.logger = get_logger()

        cls.api_key = "test_key"
        cls.port = 8200
        cls.ipus = 1
        cls.ssf_image = "graphcore/simple-server-framework:latest"

        cls.deploy_name = None
        cls.config_file = None

        cls.configure(cls)

        assert cls.deploy_name is not None
        assert cls.config_file is not None

    def teardown_class(cls):
        pass

    @abstractmethod
    def configure(self):
        pass

    @classmethod
    def test_model(cls):

        logger = cls.logger

        logger.info("\n" + "-" * 20 + f" Test Model {cls.config_file}" + "-" * 20)

        if docker.is_running(cls.deploy_name, logger=logger):
            logger.warning(f"{cls.deploy_name} exists and is running - removing it")
            docker.remove(cls.deploy_name, logger=logger)

        if docker.is_stopped(cls.deploy_name, logger=logger):
            logger.warning(f"{cls.deploy_name} exists and is stopped - removing it")
            docker.remove(cls.deploy_name, logger=logger)

        args = [
            "gc-ssf",
            "--config",
            cls.config_file,
            "--port",
            str(cls.port),
            "--key",
            cls.api_key,
            "--stdout-log-level",
            "DEBUG",
            "init",
            "build",
            "package",
            "test",
        ]

        logger.info(f"Running {args}")

        try:
            result, _, _ = run_subprocess(args)
        except Exception as e:
            logger.error(f"Exception: {e}")
            result = RESULT_FAIL

        if result == RESULT_SKIPPED:
            pytest.skip("Skipped test")
            logger.info("Skipping all remaining commands")
            return

        assert result == 0

    @classmethod
    def test_model_within_ssf(cls):

        logger = cls.logger

        logger.info(
            "\n" + "-" * 20 + f" Test Model within SSF {cls.config_file}" + "-" * 20
        )

        if docker.is_running(cls.deploy_name, logger=logger):
            logger.warning(f"{cls.deploy_name} exists and is running - removing it")
            docker.remove(cls.deploy_name, logger=logger)

        if docker.is_stopped(cls.deploy_name, logger=logger):
            logger.warning(f"{cls.deploy_name} exists and is stopped - removing it")
            docker.remove(cls.deploy_name, logger=logger)

        # Mount SSF repo into docker so we can tell the container to clone and
        # run our repo-local model as if it was a remote repository/application.
        repo_config = "file:///ssf|" + cls.config_file
        docker_args = ["-v", f"{os.getcwd()}:/ssf"]

        ssf_options = (
            f"--config {repo_config} -p {cls.port} --key {cls.api_key} init build run"
        )

        if not docker.start(
            cls.deploy_name,
            cls.ssf_image,
            ipus=cls.ipus,
            ssf_options=ssf_options,
            docker_args=docker_args,
            logger=logger,
        ):
            raise ValueError(f"Failed Start")

        # Run application testing against the SSF container we just started.
        # We can use SSF itself again here to pull the application repo and run its tests.
        args = [
            "gc-ssf",
            "--config",
            cls.config_file,
            "--deploy-name",
            cls.deploy_name,
            "--port",
            str(cls.port),
            "--key",
            cls.api_key,
            "--stdout-log-level",
            "DEBUG",
            "init",
            "test",
            "--test-skip-start",
        ]

        logger.info(f"Running {args}")

        try:
            result, _, _ = run_subprocess(args)
        except Exception as e:
            logger.error(f"Exception: {e}")
            result = RESULT_FAIL

        if result == RESULT_SKIPPED:
            logger.info("Skipping all remaining commands")
            pytest.skip("Skipped test")

        assert result == 0
