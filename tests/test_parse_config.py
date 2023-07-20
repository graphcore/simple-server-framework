# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import os
import pytest
from ssf.cli import parse_config, REPO_ROOT, DEFAULT_CONFIG, GRADIENT_MODELS_ROOT


@pytest.mark.fast
def test_parse_config():

    cwd = os.path.realpath(os.path.expanduser("."))
    usr = os.path.realpath(os.path.expanduser("~/"))

    examples = [
        # ** From local source code **
        {
            "input": "myapp/ssf_config.yaml",
            "repo": None,
            "repo_dir": None,
            "repo_name": None,
            "config": os.path.join(cwd, "myapp/ssf_config.yaml"),
            "config_file": "myapp/ssf_config.yaml",
            "checkout": None,
        },
        # ** From local source code with user **
        {
            "input": "~/myapp/ssf_config.yaml",
            "repo": None,
            "repo_dir": None,
            "repo_name": None,
            "config": os.path.join(usr, "myapp/ssf_config.yaml"),
            "config_file": "~/myapp/ssf_config.yaml",
            "checkout": None,
        },
        # ** From local repository **
        {
            "input": "file:///ssf|examples/models/mnist/mnist_config.yaml",
            "repo": "file:///ssf",
            "repo_dir": REPO_ROOT,
            "repo_name": "ssf",
            "config": f"{REPO_ROOT}/ssf/examples/models/mnist/mnist_config.yaml",
            "config_file": "examples/models/mnist/mnist_config.yaml",
            "checkout": None,
        },
        # ** From remote repository **
        {
            "input": "git@github.com:graphcore/my_application.git|ssf/ssf_config.yaml",
            "repo": "git@github.com:graphcore/my_application.git",
            "repo_dir": REPO_ROOT,
            "repo_name": "my_application",
            "config": f"{REPO_ROOT}/my_application/ssf/ssf_config.yaml",
            "config_file": "ssf/ssf_config.yaml",
            "checkout": None,
        },
        # ** From remote repository with default config **
        {
            "input": "git@github.com:graphcore/my_application.git",
            "repo": "git@github.com:graphcore/my_application.git",
            "repo_dir": REPO_ROOT,
            "repo_name": "my_application",
            "config": f"{REPO_ROOT}/my_application/{DEFAULT_CONFIG}",
            "config_file": "ssf_config.yaml",
            "checkout": None,
        },
        # ** From remote repository with checkout **
        {
            "input": "git@github.com:graphcore/my_application.git@release|ssf/ssf_config.yaml",
            "repo": "git@github.com:graphcore/my_application.git",
            "repo_dir": REPO_ROOT,
            "repo_name": "my_application",
            "config": f"{REPO_ROOT}/my_application/ssf/ssf_config.yaml",
            "config_file": "ssf/ssf_config.yaml",
            "checkout": "release",
        },
    ]

    for e in examples:
        repo, repo_dir, repo_name, config, config_file, checkout = parse_config(
            e["input"]
        )

        print("\nInput:")
        print(e)
        print("Results:")
        print("----------------------------------------------")
        print(f"repo={repo}")
        print(f"repo_dir={repo_dir}")
        print(f"repo_name={repo_name}")
        print(f"config={config}")
        print(f"config_file={config_file}")
        print(f"checkout={checkout}")
        print("----------------------------------------------")

        assert e["repo"] == repo
        assert e["repo_dir"] == repo_dir
        assert e["repo_name"] == repo_name
        assert e["config"] == config
        assert e["config_file"] == config_file
        assert e["checkout"] == checkout
