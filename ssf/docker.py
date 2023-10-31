# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import tempfile
import time
from typing import List
from ssf.utils import logged_subprocess


def is_running(application_id: str, logger=None) -> bool:
    """Test if an application container is running
    :param application_id: container name
    :param logger: use provided logger or None
    :return: Returns True iff application_id is found and state is running
    """
    with tempfile.NamedTemporaryFile(mode="w+t") as output:
        exit_code = logged_subprocess(
            "is_running",
            [
                "docker",
                "container",
                "inspect",
                "-f",
                "'{{.State.Running}}'",
                application_id,
            ],
            file_output=output,
        )
        if exit_code:
            return False
        output.seek(0)
        lines = output.readlines()
        if logger:
            logger.debug(lines)
        return lines[0].strip() == "'true'"


def is_stopped(application_id: str, logger=None) -> bool:
    """Test if an application container is stopped
    :param application_id: container name
    :param logger: use provided logger or None
    :return: Returns True iff application_id is found and state is stopped
    """
    with tempfile.NamedTemporaryFile(mode="w+t") as output:
        exit_code = logged_subprocess(
            "is_stopped",
            [
                "docker",
                "container",
                "inspect",
                "-f",
                "'{{.State.Running}}'",
                application_id,
            ],
            file_output=output,
        )
        if exit_code:
            return False
        output.seek(0)
        lines = output.readlines()
        if logger:
            logger.debug(lines)
        return lines[0].strip() == "'false'"


def start(
    application_id: str,
    package_tag: str,
    ipus: int,
    ssf_options: str,
    docker_args: List[str] = [],
    logger=None,
) -> bool:
    """Start an application container
    :param application_id: container name
    :param package_tag: docker image to start
    :param ipus: does the application require IPUs (how many)
    :param ssf_options: passed to container as SSF_OPTIONS environment variable
    :param docker_args: optional additional argument list to pass to docker run (will not be logged so may contain keys)
    :param logger: use provided logger or None
    :return: Returns True iff container is started
    """
    if logger:
        logger.info(f"SSF_OPTIONS={ssf_options}")

    docker_args = docker_args + [
        "--env",
        f"SSF_OPTIONS={ssf_options}",
        "--name",
        application_id,
        package_tag,
    ]

    with tempfile.NamedTemporaryFile(mode="w+t") as start_output:
        if ipus > 0:
            exit_code = logged_subprocess(
                "docker run",
                ["gc-docker", "--", "-d"] + docker_args,
                file_output=start_output,
            )
            if exit_code:
                if logger:
                    logger.error(
                        f"gc-docker run for {application_id} {package_tag} errored ({exit_code})"
                    )
                return False
        else:
            exit_code = logged_subprocess(
                "docker run",
                ["docker", "run", "-d", "--network", "host"] + docker_args,
                file_output=start_output,
            )
            if exit_code:
                if logger:
                    logger.error(
                        f"docker run for {application_id} {package_tag} errored ({exit_code})"
                    )
                return False

        start_output.seek(0)
        lines = start_output.readlines()
        if logger:
            logger.debug(lines)
        return True


def remove(application_id: str, logger=None) -> bool:
    """Forcably remove an application container
    :param application_id: container name
    :param logger: use provided logger or None
    :return: Returns True unless there was a docker error
    """
    with tempfile.NamedTemporaryFile(mode="w+t") as output:
        exit_code = logged_subprocess(
            "docker rm", ["docker", "rm", "-f", application_id], file_output=output
        )
        if exit_code:
            if logger:
                logger.error(f"docker stop for {application_id} errored ({exit_code})")
            return False

        output.seek(0)
        lines = output.readlines()
        if logger:
            logger.debug(lines)
        return True


def stop(application_id: str, logger=None) -> bool:
    """Stop an application container
    :param application_id: container name
    :param logger: use provided logger or None
    :return: Returns True iff application was running and is succesfully stopped
    """
    with tempfile.NamedTemporaryFile(mode="w+t") as output:
        exit_code = logged_subprocess(
            "docker stop", ["docker", "stop", application_id], file_output=output
        )
        if exit_code:
            if logger:
                logger.error(f"docker stop for {application_id} errored ({exit_code})")
            return False

        output.seek(0)
        lines = output.readlines()
        if logger:
            logger.debug(lines)
        return True


def wait_ready_from_logs(
    application_id: str, ready_magic: str, timeout: int, logger=None
) -> bool:
    """Wait for some 'magic' string to appear in the docker logs
    :param application_id: container name
    :param ready_magic: magic string that indicates the container is ready
    :param timeout: maximum time to wait for magic string in seconds
    :param logger: use provided logger or None
    :return: Returns True iff container is running and magic string is found before timeout expires
    """
    WAIT_PERIOD = 5
    INFO_PERIOD = 60

    start = time.time()
    last_info = start

    while True:
        time.sleep(WAIT_PERIOD)

        if not is_running(application_id):
            if logger:
                logger.error(f"docker container for {application_id} is not running")
            return False

        with tempfile.NamedTemporaryFile(mode="w+t") as log_output:
            # We can't tail this because we can't guarantee the application won't log something
            # after Uvicorn is ready.
            exit_code = logged_subprocess(
                "docker logs",
                ["docker", "logs", application_id],
                stdout_log_level=None,
                stderr_log_level=None,
                file_output=log_output,
            )
            if exit_code:
                if logger:
                    logger.error(
                        f"docker logs for {application_id} errored ({exit_code})"
                    )
                return False

            log_output.seek(0)
            lines = log_output.readlines()
            ready = [l for l in lines if ready_magic in l]
            if len(ready):
                return True

        now = time.time()
        elapsed = now - start
        if elapsed > timeout:
            if logger:
                logger.error(f"Timeout >{timeout} waiting for {application_id}")
            return False

        if (now - last_info) > INFO_PERIOD:
            if logger:
                logger.info(f"Log status: {lines[-1]}")
            last_info = now


def log(application_id: str, logger) -> bool:
    """Log docker container logs
    :param application_id: container name
    :param logger: use provided logger
    :return: Returns True iff container exists and logs are succesfully captured
    """
    with tempfile.NamedTemporaryFile(mode="w+t") as log_output:
        exit_code = logged_subprocess("docker logs", ["docker", "logs", application_id])
        if exit_code:
            logger.error(f"docker logs for {application_id} errored ({exit_code})")
            return False
        return True
