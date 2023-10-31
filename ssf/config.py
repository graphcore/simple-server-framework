# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from dataclasses import dataclass, field
from typing import List, Dict
from argparse import Namespace


@dataclass
class EndpointParam:
    id: str = None
    dtype: str = None
    description: str = " "
    example: str = None


@dataclass
class PackageDescription:
    name: str = None
    tag: str = None
    base_image: str = None
    docker_run: str = ""
    inclusions: List[str] = field(default_factory=lambda: [])
    exclusions: List[str] = field(default_factory=lambda: [])
    docker: Dict[str, str] = field(default_factory=lambda: {})


@dataclass
class EndpointDescription:
    index: int = None
    file: str = None
    id: str = "endpoint"
    version: str = "1"
    description: str = " "
    custom: str = None
    generate: bool = True
    http_param_format: str = None
    inputs: List[EndpointParam] = field(default_factory=lambda: [])
    outputs: List[EndpointParam] = field(default_factory=lambda: [])


@dataclass
class ApplicationDescription:
    id: str = "untitled"
    name: str = "untitled API"
    description: str = " "
    version: str = "1.0"
    license_name: str = None
    license_url: str = None
    terms_of_service: str = None
    # Application directory is the location of the config file
    dir: str = None
    # Application file is the location of the application module
    file: str = None
    file_dir: str = None
    syspaths: List[str] = field(default_factory=lambda: [])
    # IPUs required for running one instance of application
    ipus: int = 1
    # IPUs required for running application including any type of replication
    total_ipus: int = 1
    trace: bool = True
    max_batch_size: int = 1
    package: PackageDescription = None
    interface = None
    dependencies: Dict[str, str] = field(default_factory=lambda: {})
    artifacts: List[str] = field(default_factory=lambda: [])
    startup_timeout: int = 300


@dataclass
class SSFConfig:
    ssf_version: str = "0.0.1"
    config_file: str = None
    config_dict: dict = None
    endpoints: List[EndpointDescription] = field(default_factory=lambda: [])
    application: ApplicationDescription = None
    args: Namespace = None
    unknown_args: List[str] = None
    api: str = None
