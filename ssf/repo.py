# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import logging
import os
import shutil
import tempfile

from ssf.ssh import add_ssh_host
from ssf.utils import logged_subprocess, temporary_cwd
from ssf.results import SSFExceptionGitRepoError, SSFExceptionPaperspaceDeploymentError

logger = logging.getLogger()


def clone(repo_url: str, repo_dir: str, repo_name: str, checkout: str):

    if not repo_dir or repo_dir == "" or repo_dir == "./":
        raise SSFExceptionGitRepoError(f"repo_dir is not well defined {repo_dir}")

    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)
    os.makedirs(repo_dir)

    with temporary_cwd(repo_dir):
        # For repo_url with git ssh form (eg) "git@github.com:....",
        # get repo_host = "github.com", but be careful to allow other
        # forms too, such as:
        # - Local file system (eg) "file:///..."
        # - Public https (eg) "https://github.com/...."
        # - Using SSH (eg) "ssh://<user>@<host>/..."
        repo_host = repo_url.split(":")[0]
        if "git@" in repo_host:
            repo_host = repo_host.split("@")[1]
            add_ssh_host(repo_host)

        if checkout is None:
            logger.info(f"Cloning default/HEAD from {repo_url}")
            exit_code = logged_subprocess(
                "Git clone",
                [
                    "git",
                    "--no-pager",
                    "clone",
                    "--depth",
                    "1",
                    "--recurse-submodules",
                    "--shallow-submodules",
                    repo_url,
                ],
            )
            if exit_code:
                raise SSFExceptionGitRepoError(f"Git clone errored ({exit_code})")
        else:
            logger.info(f"Cloning {checkout} from {repo_url}")
            exit_code = logged_subprocess(
                "Git clone",
                [
                    "git",
                    "clone",
                    "--no-checkout",
                    "--recurse-submodules",
                    repo_url,
                ],
            )
            if exit_code:
                raise SSFExceptionGitRepoError(f"Git clone errored ({exit_code})")

            with temporary_cwd(repo_name):
                exit_code = logged_subprocess(
                    "Git checkout",
                    [
                        "git",
                        "checkout",
                        checkout,
                    ],
                )
                if exit_code:
                    raise SSFExceptionGitRepoError(
                        f"Git checkout errored ({exit_code})"
                    )

                exit_code = logged_subprocess(
                    "Git submodule update",
                    ["git", "submodule", "update", "--init", "--recursive"],
                )
                if exit_code:
                    raise SSFExceptionGitRepoError(
                        f"Git submodule update errored ({exit_code})"
                    )


def paperspace_load_model(repo_dir, model_id: str, args):

    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)
    os.makedirs(repo_dir)
    api_key = os.getenv(args.deploy_paperspace_api_key)
    if api_key is None:
        raise SSFExceptionPaperspaceDeploymentError(
            f"Please set Gradient API token using --deploy-paperspace-api-key"
        )

    with tempfile.NamedTemporaryFile(mode="w+t") as gradient_output:
        exit_code = logged_subprocess(
            "Gradient downloading model",
            [
                "gradient",
                "models",
                "download",
                "--id",
                model_id,
                "--destinationDir",
                repo_dir,
                "--apiKey",
                api_key,
            ],
            file_output=gradient_output,
        )
        if exit_code:
            raise SSFExceptionPaperspaceDeploymentError(
                f"Download Gradient model {model_id} errored ({exit_code})"
            )

        gradient_output.seek(0)
        lines = gradient_output.readlines()
        logger.debug(lines)
        # Downloading: <path>
        try:
            deployment = lines[0].strip()
            deployment = deployment.split(":")
            if deployment[0].strip() == "Downloading":
                zip_path = deployment[1].strip()
            else:
                raise
            if ".zip" not in zip_path:
                raise SSFExceptionPaperspaceDeploymentError(
                    "Model from Gradient must be a .zip archive."
                )
            else:
                full_zip_path = os.path.join(repo_dir, zip_path)
                exit_code = logged_subprocess(
                    "Unzipping", ["unzip", full_zip_path, "-d", repo_dir]
                )
                assert exit_code <= 1

        except Exception as e:
            raise SSFExceptionPaperspaceDeploymentError(
                f"Failed to unpack Gradient model {model_id}."
            ) from e
        return None
