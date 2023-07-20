# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import logging
import os
import shutil
import tempfile

from ssf.ssh import add_ssh_host
from ssf.utils import logged_subprocess, temporary_cwd

logger = logging.getLogger()


def clone(repo_url: str, repo_dir: str, repo_name: str, checkout: str):

    if not repo_dir or repo_dir == "" or repo_dir == "./":
        raise ValueError(f"repo_dir is not well defined {repo_dir}")

    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)
    os.makedirs(repo_dir)

    with temporary_cwd(repo_dir):
        # For repo_url = (eg) git@github.com:....
        # Get repo_host = github.com
        # Supports local form (eg) "file:///..."
        # TODO:
        # Check if this format parsing will be robust.
        repo_host = repo_url.split(":")[0]

        if repo_host != "file":
            sep = repo_host.find("@")
            if sep != -1:
                repo_host = repo_host[sep + 1 :]
            if repo_host:
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
                raise ValueError(f"Git clone errored {exit_code}")
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
                raise ValueError(f"Git clone errored {exit_code}")

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
                    raise ValueError(f"Git checkout errored {exit_code}")

                exit_code = logged_subprocess(
                    "Git submodule update",
                    ["git", "submodule", "update", "--init", "--recursive"],
                )
                if exit_code:
                    raise ValueError(f"Git submodule update errored {exit_code}")
