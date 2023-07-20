# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
from typing import List, Tuple

from ssf.config import SSFConfig
from ssf.publish import docker_login_command, docker_logout_command
from ssf.results import *
from ssf.ssh import add_ssh_host
from ssf.utils import logged_subprocess

logger = logging.getLogger("ssf")


def deploy(
    ssf_config: SSFConfig,
    application_id: str,
    package_tag: str,
    name: str,
    ssf_options: List[str],
    add_env: List[Tuple[str, str]],
    total_application_ipus: int,
):
    logger.info("> ==== Deploy Gcore ====")

    args = ssf_config.args

    deploy_gcore_target_address = args.deploy_gcore_target_address
    deploy_gcore_target_username = args.deploy_gcore_target_username

    boot_file = f"{application_id}-boot.sh"

    with open(boot_file, "w") as boot:

        boot.write("#!/usr/bin/env bash\n")
        config_cmd = ""
        # Optional - Login docker before pulling image.
        if args.docker_username and args.docker_password:
            # NOTE:
            # The docker password is referenced from an environement variable rather
            # than baking it into the script; it must be set when the script is run.
            boot.write('echo "Login docker repository:"\n')
            _, cmd, pwd, config_path = docker_login_command(ssf_config)
            boot.write('echo "$DOCKER_PASSWORD" | ' + " ".join(cmd) + "\n")
            config_cmd = "--config" + " " + config_path

        # Pull docker image package_tag.
        boot.write(f'echo "Pulling {package_tag}:"\n')
        boot.write(f"if ! docker {config_cmd} pull {package_tag}; then\n")
        boot.write(f'  echo "ERROR: Failed to pull package image {package_tag}"\n')
        boot.write("  exit 1\n")
        boot.write("fi\n")

        # Log out from Docker
        if args.docker_username and args.docker_password:
            boot.write(f'  echo "Logging out from Docker registry"\n')
            _, logout_cmd = docker_logout_command(ssf_config)
            boot.write(" ".join(logout_cmd) + "\n")
            boot.write(f"rm -r {config_path}" + "\n")

        # Stop/remove running container (if any)
        boot.write(
            f"if [ \"$( docker container inspect -f '{{{{.State.Status}}}}' {name} 2> /dev/null )\" ]; then\n"
        )
        boot.write(f'  echo "Stopping current {name} container:"\n')
        boot.write(f"  docker rm -f {name}\n")
        boot.write("fi\n")

        # Run container.
        # NOTE:
        # Each environment variables is referenced from the environement variable rather
        # than baking it into the script; it must be set when the script is run.
        boot.write(f'echo "Running {name} container:"\n')
        if total_application_ipus > 0:
            docker_run = "gc-docker -- -d "
        else:
            docker_run = "docker run -d --network host"
        boot.write(f"if ! {docker_run} \\\n")
        for e in add_env:
            boot.write(f'  --env {e[0]}="${{{e[0]}}}" \\\n')
        options = "\\\n  ".join(ssf_options)
        boot.write(f'  --env SSF_OPTIONS="{options}" \\\n')
        boot.write(f"  --name {name} {package_tag}; then\n")
        boot.write(f'  echo "ERROR: Failed to run package image {package_tag}"\n')
        boot.write("  exit 2\n")
        boot.write("fi\n")
        boot.write("sleep 2\n")
        boot.write('echo "Startup logs:"\n')
        boot.write(f"docker logs {name}\n")
        boot.write('echo "..."\n')
        boot.write(f'docker inspect {name} --format="{{{{.State}}}}"\n')
        boot.write(
            f'RUNNING=$(docker inspect {name} --format="{{{{.State.Running}}}}")\n'
        )
        boot.write('echo "RUNNING:${RUNNING}"\n')
        boot.write('if [ "${RUNNING}" == "true" ]; then\n')
        boot.write(f'  echo "{name} is running"\n')
        boot.write('  echo "Docker processes:"\n')
        boot.write("  docker ps\n")
        boot.write("  exit 0\n")
        boot.write("else\n")
        boot.write(f'  echo "ERROR: {name} is not running"\n')
        boot.write("  exit 1\n")
        boot.write("fi\n")

    with open(boot_file, "r") as boot:
        boot = boot.readlines()
        for line in boot:
            line = line.rstrip()
            logger.debug("Boot script> " + line)

    if deploy_gcore_target_address:
        # ssh run it, passing through keys
        logger.info(
            f"Deploying with username {deploy_gcore_target_username} and address {deploy_gcore_target_address}"
        )

        add_ssh_host(deploy_gcore_target_address)

        if deploy_gcore_target_username:
            target = f"{deploy_gcore_target_username}@{deploy_gcore_target_address}"
        else:
            target = deploy_gcore_target_address

        with open(boot_file, "r") as boot:
            boot = boot.readlines()
            cmds = ["ssh", f"{target}"]
            # Pass through docker password and enviroment variables.
            if args.docker_username and args.docker_password:
                cmds.append(f'export DOCKER_PASSWORD="{args.docker_password}";')
            for e in add_env:
                cmds.append(f'export {e[0]}="{e[1]}";')
            cmds.extend(["bash", "-s"]),

            exit_code = logged_subprocess(
                "Execute boot file", cmds, piped_input="".join(boot).encode()
            )
        if exit_code:
            logger.error(f"Execute file {boot_file} at {target} errored {exit_code}")
            raise ValueError(
                f"Failed to execute boot file {boot_file} at {target} {exit_code}"
            )

        logger.info(f"Executed file {boot_file} at {target} {exit_code}")
        logger.info(f'> Started {package_tag} as "{name}" at {target}')
    else:
        logger.warning("No deploment target specified")

    return RESULT_OK
