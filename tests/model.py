# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# import os
from abc import ABC, abstractmethod
import logging
import os
import pytest
import sys
from ssf.utils import API_FASTAPI

from utils import run_subprocess
import ssf.docker as docker
from ssf.results import *
from ssf.version import VERSION, ID

# NOTE:
# The test_model_within_ssf set of tests run the model within a published SSF container.
# 1/ Running from the published release repository => corresponding public SSF image.
# 2/ Running from the private development repository => current development SSF image.
# In either case, the corresponding image must have been pulled locally before these
# tests are run.


def get_latest_public_ssf_image():
    return f"graphcore/{ID}:{VERSION}"


def get_current_development_ssf_image():
    return f"graphcore/cloudsolutions-dev:{ID}-{VERSION}"


def is_development_repo():
    return os.path.isfile(".pre-commit-config.yaml")


def get_default_ssf_image():
    if is_development_repo():
        return get_current_development_ssf_image()
    else:
        return get_latest_public_ssf_image()


def check_image_available():
    try:
        image = get_default_ssf_image()
        result, _, _ = run_subprocess(["docker", "inspect", "--type=image", image])
        if result == 0:
            print(f"Image {image} found")
            return True
        else:
            print(f"Image {image} not found")
            return False
    except Exception as e:
        print("Failed find image")
    return False


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
        cls.ipus = 1
        cls.ssf_image = get_default_ssf_image()

        cls.deploy_name = None
        cls.config_file = None

        cls.configure(cls)

        assert cls.deploy_name is not None
        assert cls.config_file is not None

    @pytest.fixture(scope="class", autouse=True)
    def set_port(self, pytestconfig):
        type(self).port = pytestconfig.getoption("port")

    def teardown_class(cls):
        pass

    @abstractmethod
    def configure(self):
        pass

    @classmethod
    def test_model(cls, api=API_FASTAPI):

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
            "--api",
            api,
            "--stdout-log-level",
            "DEBUG",
            "--stop-on-error",
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
            logger.info("Skipping all remaining commands")
            pytest.skip("Skipped test (SSF RESULT_SKIPPED)")

        assert result == 0

    @classmethod
    def test_model_within_ssf(cls, api=API_FASTAPI):

        logger = cls.logger

        logger.info(
            "\n"
            + "-" * 20
            + f" Test Model within SSF {cls.config_file} {cls.ssf_image}"
            + "-" * 20
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

        ssf_options = f"--config {repo_config} -p {cls.port} --key {cls.api_key} --api {api} --stop-on-error init build run"

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
            "--api",
            api,
            "--stdout-log-level",
            "DEBUG",
            "--stop-on-error",
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
