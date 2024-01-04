# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import atexit
import logging
import os
import tempfile
from typing import List, Tuple
import sys
import shutil

from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import (
    RESULT_OK,
    SSFExceptionPaperspaceDeploymentError,
)

from ssf.utils import logged_subprocess

logger = logging.getLogger("ssf")

GRADIENT_VENV_DIR = ".gradient_venv"


def prepare_gradient_venv():
    environ = os.environ
    environ["PATH"] = os.path.join(GRADIENT_VENV_DIR, "bin") + ":" + environ["PATH"]
    if not os.path.isdir(GRADIENT_VENV_DIR):
        logger.info(
            "> One-time preparation of environment with Gradient for Paperspace deployment"
        )
        result = logged_subprocess(
            "Create Gradient virtual environement",
            [sys.executable, "-m", "venv", GRADIENT_VENV_DIR],
        )
        if result == 0:
            result = logged_subprocess(
                "Install Gradient", ["pip3", "install", "gradient"], environ=environ
            )
        if result != 0:
            logger.error(
                "Failed one-time preparation of environment with Gradient for Paperspace deployment"
            )
            shutil.rmtree(GRADIENT_VENV_DIR)
    return environ


def deploy(
    ssf_config: SSFConfig,
    application_id: str,
    package_tag: str,
    name: str,
    ssf_options: List[str],
    add_env: List[Tuple[str, str, str]],
    total_application_ipus: int,
):
    logger.info("> ==== Deploy Paperspace ====")

    args = ssf_config.args

    project_id = args.deploy_paperspace_project_id
    cluster_id = args.deploy_paperspace_cluster_id
    api_key_env = args.deploy_paperspace_api_key
    spec_file = args.deploy_paperspace_spec_file
    containerRegistry = args.deploy_paperspace_registry
    replicas = args.deploy_paperspace_replicas

    if not project_id:
        raise SSFExceptionPaperspaceDeploymentError(
            f"Deployment project id must be specified"
        )
    if not cluster_id:
        raise SSFExceptionPaperspaceDeploymentError(
            f"Deployment cluster id must be specified"
        )
    if not api_key_env:
        raise SSFExceptionPaperspaceDeploymentError(
            f"Deployment API key must be specified"
        )
    try:
        api_key = os.getenv(api_key_env)
        assert api_key
    except:
        raise SSFExceptionPaperspaceDeploymentError(
            f"Deployment API key '{api_key_env}' must be set in environment"
        )

    environ = prepare_gradient_venv()

    def get_existing_instance_id():
        with tempfile.NamedTemporaryFile(mode="w+t") as gradient_output:
            try:
                exit_code = logged_subprocess(
                    "Gradient deployments list",
                    [
                        "gradient",
                        "deployments",
                        "list",
                        "--name",
                        name,
                        "--projectId",
                        project_id,
                        "--clusterId",
                        cluster_id,
                        "--apiKey",
                        api_key,
                    ],
                    file_output=gradient_output,
                    environ=environ,
                )
            except Exception as e:
                logger.exception(e)
                return None

            gradient_output.seek(0)
            lines = gradient_output.readlines()
            # +-------------+--------------------------------------+
            # | Name        | ID                                   |
            # +-------------+--------------------------------------+
            # | simple_test | 7c16c005-2de3-4e15-817d-de01bc117f74 |
            # +-------------+--------------------------------------+
            logger.debug(lines)
            try:
                for line in lines:
                    if name in line:
                        instance = line.strip()
                        instance = instance.split("|")
                        return instance[2].strip()
            except:
                pass
            logger.debug("Did not find existing deployment")
            return None

    def create_deployment():
        with tempfile.NamedTemporaryFile(mode="w+t") as gradient_output:
            try:
                exit_code = logged_subprocess(
                    "Gradient deployments create",
                    [
                        "gradient",
                        "deployments",
                        "create",
                        "--name",
                        name,
                        "--projectId",
                        project_id,
                        "--clusterId",
                        cluster_id,
                        "--apiKey",
                        api_key,
                        "--spec",
                        spec_file,
                    ],
                    file_output=gradient_output,
                    environ=environ,
                )
            except Exception as e:
                logger.exception(e)
                return None

            gradient_output.seek(0)
            lines = gradient_output.readlines()
            # Created deployment: 7c16c005-2de3-4e15-817d-de01bc117f74
            logger.debug(lines)
            try:
                deployment = lines[0].strip()
                deployment = deployment.split(":")
                if deployment[0].strip() == "Created deployment":
                    return deployment[1].strip()
            except:
                pass
            logger.error("Failed to create deployment")
            return None

    def update_deployment(instance_id):
        with tempfile.NamedTemporaryFile(mode="w+t") as gradient_output:
            try:
                exit_code = logged_subprocess(
                    "Gradient deployments update",
                    [
                        "gradient",
                        "deployments",
                        "update",
                        "--id",
                        instance_id,
                        "--apiKey",
                        api_key,
                        "--spec",
                        spec_file,
                    ],
                    file_output=gradient_output,
                    environ=environ,
                )
            except Exception as e:
                logger.exception(e)
                return None

            gradient_output.seek(0)
            lines = gradient_output.readlines()
            logger.debug(lines)
            # Updated deployment: 7c16c005-2de3-4e15-817d-de01bc117f74
            try:
                deployment = lines[0].strip()
                deployment = deployment.split(":")
                if deployment[0].strip() == "Updated deployment":
                    return deployment[1].strip()
            except:
                pass
            logger.error("Failed to update deployment")
            return None

    logger.info(
        f"> Deploying {name} to {args.deploy_platform} (ProjectID {project_id} ClusterID {cluster_id})"
    )

    generated_spec_file = False

    if not spec_file:
        generated_spec_file = True
        spec_file = f"{application_id}_deploy.yaml"

        # The spec file isn't required once the deployment is created
        # or updated. Make sure it is deleted since it may contain SSH
        # keys in plain text. For debug purposes, the generated spec
        # file is still logged but with secrets masked.
        def _delete_spec_file():
            try:
                os.remove(spec_file)
            except:
                pass

        def delete_spec_file():
            _delete_spec_file()
            atexit.unregister(_delete_spec_file)

        atexit.register(_delete_spec_file)

        # TBC:
        # total_application_ipus might be zero, in which case we could create a CPU instance type here.
        if total_application_ipus <= 4:
            instance_type = "IPU-POD4"
        elif total_application_ipus <= 16:
            instance_type = "IPU-POD16"
        else:
            raise SSFExceptionPaperspaceDeploymentError(
                f"Cannot satisfy deployment of application using {total_application_ipus} IPUs"
            )
        logger.info(
            f"Requesting {instance_type} to serve {total_application_ipus} IPUS"
        )

        MARKUP_SECRET_VALUE_BEGIN = "#SECRET VALUE BEGIN"
        MARKUP_SECRET_VALUE_END = "#SECRET VALUE END"

        with open(spec_file, "w") as spec:
            spec.write("enabled: true\n")
            spec.write(f"image: {package_tag}\n")
            spec.write(f"containerRegistry: {containerRegistry}\n")
            spec.write(f"port: {args.port}\n")
            spec.write("env:\n")
            if len(ssf_options):
                spec.write("  - name: SSF_OPTIONS\n")
                spec.write(f"    value: \"{' '.join(ssf_options)}\"\n")
                for e in add_env:
                    spec.write(f"  - name: {e[0]}\n")
                    markup_secret = "secret" in e[2]
                    if markup_secret:
                        spec.write(f"{MARKUP_SECRET_VALUE_BEGIN}\n")
                    if "\n" in e[1]:
                        spec.write(f"    value: |-\n")
                        for line in e[1].split("\n"):
                            spec.write(f"      {line}\n")
                    else:
                        spec.write(f'    value: "{e[1]}"\n')
                    if markup_secret:
                        spec.write(f"{MARKUP_SECRET_VALUE_END}\n")
            spec.write("resources:\n")
            spec.write(f"  replicas: {replicas}\n")
            spec.write(f"  instanceType: {instance_type}\n")

        # Log the final spec file, but be careful to avoid
        # leaking any secrets (e.g. SSH keys).
        with open(spec_file, "r") as spec:
            spec = spec.readlines()
            hide = False
            for line in spec:
                line = line.rstrip()
                if line == MARKUP_SECRET_VALUE_BEGIN:
                    hide = True
                    logger.debug("Spec>     value: ##############")
                elif line == MARKUP_SECRET_VALUE_END:
                    hide = False
                elif not hide:
                    logger.debug("Spec> " + line)

    instance_id = get_existing_instance_id()

    if instance_id:
        logger.info(f"> Updating existing deployment with id {instance_id}")
        updated_instance_id = update_deployment(instance_id)
        if updated_instance_id:
            logger.info(f"> Deployment updated {updated_instance_id}")
        else:
            raise SSFExceptionPaperspaceDeploymentError(
                f"Failed to update deployment {instance_id}"
            )
    else:
        logger.info("> Creating new deployment")
        created_instance_id = create_deployment()
        if created_instance_id:
            logger.info(f"> Deployment created {created_instance_id}")
        else:
            raise SSFExceptionPaperspaceDeploymentError(f"Failed to create deployment")

    if generated_spec_file:
        delete_spec_file()

    return RESULT_OK
