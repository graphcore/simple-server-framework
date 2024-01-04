# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import atexit
import logging
import requests
import time
import os

from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import *
from ssf.application_interface.application import get_application_test

from ssf.app_venv import create_app_venv
from ssf.package import get_package_name_and_tag
from ssf.utils import (
    API_FASTAPI,
    API_GRPC,
    get_supported_apis,
    poplar_version_ok,
    get_poplar_requirement,
    temporary_cwd,
    get_ipu_count_requirement,
    ipu_count_ok,
)
import ssf.docker as docker
from ssf.grpc_runtime.test_utils_grpc import GRPCSession
from ssf.sdk_utils import maybe_activate_poplar_sdk

logger = logging.getLogger("ssf")


def test(ssf_config: SSFConfig):
    logger.info("> ==== Test ====")
    env = maybe_activate_poplar_sdk(ssf_config)
    if not poplar_version_ok(ssf_config, env):
        raise SSFExceptionUnmetRequirement(
            f"Missing or unsupported Poplar version - needs {get_poplar_requirement(ssf_config)}"
        )
    if not ipu_count_ok(ssf_config, "test", env):
        raise SSFExceptionUnmetRequirement(
            f"IPUs count does not match application requirements."
        )

    # TODO:
    # This currently assumes FastAPI/Uvicorn.
    # We should adjust for API here.
    supported_apis = get_supported_apis()
    if ssf_config.args.api not in supported_apis:
        raise SSFExceptionUnmetRequirement(
            f"Missing or unsupported API {ssf_config.args.api} - needs one of {supported_apis}"
        )

    application_id = ssf_config.application.id

    if ssf_config.args.deploy_name:
        name = ssf_config.args.deploy_name
    else:
        name = application_id

    _, package_tag = get_package_name_and_tag(ssf_config)

    try:
        startup_timeout = ssf_config.application.startup_timeout
    except:
        startup_timeout = 600

    # Override key for testing.
    API_KEY = ssf_config.args.key
    if API_KEY is None:
        API_KEY = "test_key"

    PORT = ssf_config.args.port
    IP = "0.0.0.0"
    HOST = f"http://{IP}"
    IPADDR = f"{HOST}:{PORT}"

    def subtest_check_server_ready(session, startup_timeout):
        WAIT_PERIOD = 20
        INFO_PERIOD = 120

        start = time.time()
        last_info = start

        MAGIC1 = 200

        logger.info(f"Waiting for server ready (timeout {startup_timeout}s)")
        time.sleep(WAIT_PERIOD / 4)

        while True:

            if not docker.is_running(name):
                if logger:
                    logger.error(f"docker container {name} is not running")
                return False

            try:
                response = session.get(f"{IPADDR}/health/ready")
                logger.debug(f"{response.status_code} {response.text}")
                if response.status_code == MAGIC1:
                    return True
            except:
                pass

            time.sleep(WAIT_PERIOD)

            now = time.time()
            elapsed = now - start

            if elapsed > startup_timeout:
                logger.error("Timeout waiting for server ready")
                return False

            if (now - last_info) > INFO_PERIOD:
                if logger:
                    logger.info(
                        f"Still waiting for server ready ({int(elapsed)}/{startup_timeout}s)"
                    )
                last_info = now

    def subtest_check_root_endpoint(session) -> bool:
        MAGIC1 = 200
        MAGIC2 = '{"message":"OK"}'
        try:
            response = session.get(
                IPADDR, headers={"accept": "application/json"}, timeout=5
            )
            logger.debug(f"{response.status_code} {response.text}")
            return response.status_code == MAGIC1 and response.text == MAGIC2
        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return False

    def subtest_check_security_logout(session):
        MAGIC1 = 200
        MAGIC2 = '{"message":"OK"}'
        MAGIC3 = 307  # Redirect
        try:
            response = session.get(
                f"{IPADDR}/logout", headers={"accept": "application/json"}, timeout=5
            )
            logger.debug(f"{response.status_code} {response.text} {response.history}")
            return (
                response.status_code == MAGIC1
                and response.text == MAGIC2
                and response.history[0].status_code == MAGIC3
            )
        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return False

    def subtest_check_security_forbidden(session):
        MAGIC1 = 403
        MAGIC2 = "Invalid credentials"
        try:
            response = session.get(
                f"{IPADDR}/login",
                data={"api_key": "bogus"},
                headers={"accept": "application/json"},
                timeout=5,
            )
            logger.debug(f"{response.status_code} {response.text}")
            return response.status_code == MAGIC1 and MAGIC2 in response.text
        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return False

    def subtest_check_security_accepted(session):
        MAGIC1 = 200
        MAGIC2 = '{"message":"OK"}'
        MAGIC3 = 307  # Redirect
        try:
            response = session.get(
                f"{IPADDR}/login",
                params={"api_key": API_KEY},
                headers={"accept": "application/json"},
                timeout=5,
            )
            logger.debug(f"{response.status_code} {response.text} {response.history}")
            return (
                response.status_code == MAGIC1
                and response.text == MAGIC2
                and response.history[0].status_code == MAGIC3
            )
        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return False

    if ssf_config.args.test_skip_start:
        logger.info(f"> Skipping start")
    else:
        # Start it.
        logger.info(f"> Start {name} {package_tag}")
        if docker.is_running(name, logger=logger):
            raise SSFExceptionDockerStatusError(
                f"{name} exists and is running - use 'docker rm -f {name}' first"
            )
        if docker.is_stopped(application_id, logger=logger):
            raise SSFExceptionDockerStatusError(
                f"{name} exists and is stopped - use 'docker rm {name}' first"
            )
        if not docker.start(
            name,
            package_tag,
            ipus=get_ipu_count_requirement(ssf_config),
            ssf_options=f"-p {PORT} --key {API_KEY} --api {ssf_config.args.api}",
            logger=logger,
            env=env,
        ):
            raise SSFExceptionDockerStatusError(f"Failed Start")

    # Always stop container at exit unless test_skip_stop is set
    # (even if we didn't start the container).
    if not ssf_config.args.test_skip_stop:

        def docker_postfix_remove():
            logger = logging.getLogger()
            logger.info(f"> Remove {name}")
            docker.remove(name, logger=logger)

        def atexit_docker_remove():
            logger = logging.getLogger()
            logger.debug(f"atexit_docker_remove handler")
            docker_postfix_remove()

        atexit.register(atexit_docker_remove)

    # Always report docker logs at exit.
    def docker_postfix_logs():
        logger = logging.getLogger()
        logger.info(f"> Docker logs {name}")
        logger.setLevel(logging.DEBUG)
        logger.debug(
            "====================================================================================================="
        )
        docker.log(name, logger=logger)
        logger.debug(
            "====================================================================================================="
        )

    def atexit_docker_logs():
        logger = logging.getLogger()
        logger.debug(f"atexit_docker_logs handler")
        docker_postfix_logs()

    atexit.register(atexit_docker_logs)

    # Pass/failed subtests.
    subtest_ok = 0
    subtest_ko = 0

    def ok():
        nonlocal subtest_ok
        subtest_ok += 1

    def ko():
        nonlocal subtest_ko
        subtest_ko += 1

    if ssf_config.args.api == API_FASTAPI:
        session = requests.session()
    elif ssf_config.args.api == API_GRPC:
        session = GRPCSession(IP, PORT, API_KEY)

    logger.info(f"> Subtest Check server ready")
    if subtest_check_server_ready(session, startup_timeout):
        ok()
    else:
        ko()
        logger.error("Failed subtest_check_server_ready")

    logger.info(f"> Subtest Check root endpoint")
    if subtest_check_root_endpoint(session):
        ok()
    else:
        ko()
        logger.error("Failed subtest_check_root_endpoint")

    logger.info(f"> Subtest Check security logout")
    if subtest_check_security_logout(session):
        ok()
    else:
        ko()
        logger.error("Failed subtest_check_security_logout")

    logger.info(f"> Subtest Check security forbidden")
    if subtest_check_security_forbidden(session):
        ok()
    else:
        ko()
        logger.error("Failed subtest_check_security_forbidden")

    logger.info(f"> Subtest Check security accepted")
    if subtest_check_security_accepted(session):
        ok()
    else:
        ko()
        logger.error("Failed subtest_check_security_accepted")

    logger.info(f"Checking application venv")
    create_app_venv(ssf_config)

    application_test = get_application_test(ssf_config)
    if application_test:
        logger.info("> Running application tests")
        app_file_dir = ssf_config.application.file_dir
        logging.info(f"Running application test from {app_file_dir}")
        with temporary_cwd(app_file_dir):
            logger.info("Begin application tests")
            result = application_test.begin(session, IPADDR)
            if result == 0:
                ok()
                index = 0
                while True:
                    try:
                        result, desc, more = application_test.subtest(
                            session, IPADDR, index
                        )
                    except Exception as e:
                        logger.exception(e)
                        logger.error(
                            f"Application subtest failed with {e}. Terminating subtests."
                        )
                        result = False
                        desc = f"Exception {e}"
                        more = False
                    logger.info(f"{index},{result},{desc},{more}")
                    if result:
                        ok()
                    else:
                        ko()
                    if not more:
                        break
                    index += 1
                logger.info("End application tests")
                result = application_test.end(session, IPADDR)
                if result == 0:
                    ok()
                else:
                    ko()
                    logger.error("Failed to end application tests")
            else:
                ko()
                logger.error("Failed to begin application tests")
    else:
        logger.warning(f"No application specific tests")

    logger.info(f"OK {subtest_ok} KO {subtest_ko}")

    atexit.unregister(atexit_docker_logs)
    docker_postfix_logs()

    if ssf_config.args.test_skip_stop:
        logger.info(f"> Skipping stop")
    else:
        atexit.unregister(atexit_docker_remove)
        docker_postfix_remove()

    OK = subtest_ok and not subtest_ko
    if not OK:
        raise SSFExceptionApplicationTestError(
            f"{name} failed testing OK:{subtest_ok} KO:{subtest_ko}"
        )

    return RESULT_OK
