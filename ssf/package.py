# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import os
import shutil
import stat
from typing import List

from ssf.template import TemplateSymbolParser, expand_template
from ssf.utils import logged_subprocess, build_file_list, temporary_cwd
from ssf.config import SSFConfig
from ssf.results import *
from ssf.version import VERSION, ID, NAME

logger = logging.getLogger("ssf")

PACKAGE_ROOT = ".package"


def get_package_name_and_tag(ssf_config: SSFConfig, app_default: bool = True):
    # Package name and tag from config unless overridden via CLI.
    package_name = None
    package_tag = None
    if ssf_config.args.package_name:
        package_name = ssf_config.args.package_name
    elif app_default:
        package_name = ssf_config.application.package.name
    if ssf_config.args.package_tag:
        package_tag = ssf_config.args.package_tag
    elif app_default:
        package_tag = ssf_config.application.package.tag
    return package_name, package_tag


# Define a custom parser for the Dockerfile template.
class DockerFileSymbolParser(TemplateSymbolParser):
    def __init__(self, ssf_config: SSFConfig):
        self.ssf_config = ssf_config

    def parse(self, symbol_id: str, indent: int = 0) -> str:
        if symbol_id == "baseimage":
            return self.ssf_config.application.package.base_image
        if symbol_id == "ssf_version":
            return VERSION
        if symbol_id == "ssf_id":
            return ID
        if symbol_id == "ssf_name":
            return NAME


def package(ssf_config: SSFConfig):
    logger.info("> ==== Package ====")

    try:
        application_id = ssf_config.application.id

        package_name, package_tag = get_package_name_and_tag(ssf_config)

        # Where ssf source are.
        ssf_dir = str(os.path.dirname(os.path.abspath(__file__)))

        # This is where we want to build the package.
        package_dir = os.path.join(
            os.path.abspath(os.getcwd()), os.path.join(PACKAGE_ROOT, application_id)
        )

        # This is the location for sources in the package.
        package_src_dir = os.path.join(package_dir, "src")

        dockerfile_template_filename = "dockerfile.template"

        logger.info(f"> Packaging {application_id} to {package_dir}")
        logger.info(f"> Package name {package_name}")
        logger.info(f"> Package tag {package_tag}")

        if os.path.exists(package_dir):
            shutil.rmtree(package_dir)
        os.makedirs(package_dir)

        def package_decl(
            src_dir: str,
            dst_dir: str,
            include: List[str],
            exclude: List[str],
            always: List[str] = [],
            warn_on_empty_inclusions: bool = True,
            warn_on_empty_exclusions: bool = True,
        ):
            src_dir, root_src_dir, files = build_file_list(
                src_dir,
                include,
                exclude,
                always,
                warn_on_empty_inclusions,
                warn_on_empty_exclusions,
            )

            # Move each found file to the destination with relative path from src_dir.
            for src in files:
                dst = os.path.join(dst_dir, os.path.relpath(src, root_src_dir))
                logger.debug(f"Package {src} -> {dst}")

                dir = os.path.dirname(dst)
                if not os.path.exists(dir):
                    os.makedirs(dir)
                shutil.copy2(src, dst)

            # Returns relative src_dir
            return os.path.relpath(src_dir, root_src_dir)

        # Package ssf modules.
        logger.info(f"> Package SSF from {ssf_dir}")
        ssf_dst_dir = os.path.join(package_src_dir, "ssf")
        package_decl(
            src_dir=ssf_dir,
            dst_dir=ssf_dst_dir,
            include=["**/*"],
            exclude=["**/__pycache__/**", "**/__pycache__"],
            warn_on_empty_inclusions=True,
            warn_on_empty_exclusions=False,
        )
        package_decl(
            src_dir=os.path.abspath(os.path.join(ssf_dir, os.pardir)),
            dst_dir=ssf_dst_dir,
            include=["LICENSE"],
            exclude=[],
            warn_on_empty_inclusions=True,
            warn_on_empty_exclusions=False,
        )
        package_decl(
            src_dir=os.path.abspath(os.path.join(ssf_dir, os.pardir)),
            dst_dir=os.path.join(ssf_dst_dir, os.pardir),
            include=["pyproject.toml", "README.md"],
            exclude=[],
            warn_on_empty_inclusions=True,
            warn_on_empty_exclusions=False,
        )

        # Application.

        # Where the user's application sources are.
        app_dir = ssf_config.application.dir

        requirements_path = os.path.join(
            package_src_dir, "ssf_package_requirements.txt"
        )
        requirements_file = open(requirements_path, "w+")
        # Currently empty (ssf explicitly installed, dependencies via pyproject.toml)
        requirements_file.close()

        if app_dir:
            # Some expected files that we can always include.
            # (even if they aren't added in package decls)
            app_config = os.path.basename(os.path.realpath(ssf_config.config_file))
            app_module = ssf_config.application.file
            app_requirements = ssf_config.application.dependencies.get("python", None)
            if not app_requirements or not ".txt" in app_requirements:
                app_requirements = None

            # Always include these app default files.
            always = []
            always.append(app_config)
            always.append(app_module)
            if app_requirements:
                always.append(app_requirements)

            include = ssf_config.application.package.inclusions
            exclude = ssf_config.application.package.exclusions

            logger.info(f"> Package Application from {app_dir}")
            rel_src_dir = package_decl(
                src_dir=app_dir,
                dst_dir=os.path.join(package_src_dir, "app"),
                include=include,
                exclude=exclude,
                always=always,
                warn_on_empty_inclusions=True,
                warn_on_empty_exclusions=True,
            )

            app_config_package_path = os.path.join(
                "app", os.path.join(rel_src_dir, app_config)
            )

            # Endpoint files.
            logger.info(f"> Package Endpoint files")
            for endpoint in [e for e in ssf_config.endpoints if e.generate]:
                src = endpoint.file
                dst = package_src_dir
                logger.debug(f"Package {src} -> {dst}")
                if not os.path.isfile(src):
                    raise SSFExceptionPackagingError(
                        f"Missing endpoint file {src}. Use `build` to rebuild endpoint files."
                    )
                shutil.copy2(src, dst)

            # Generate a 'run.sh' in src/
            run_script = os.path.join(package_src_dir, "run.sh")
            with open(run_script, "w") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write('eval "$(ssh-agent -s)"\n')
                f.write(f"gc-ssf --config {app_config_package_path} run $SSF_OPTIONS\n")
            st = os.stat(run_script)
            os.chmod(run_script, st.st_mode | stat.S_IEXEC)

            # Gather Python requirements
            logger.info(f"> Gathering pip requirements")
            requirements_file = open(requirements_path, "a+")
            python_dependencies = ssf_config.application.dependencies.get(
                "python", None
            )
            if not python_dependencies is None:
                if ".txt" in python_dependencies:
                    for line in open(
                        os.path.join(app_dir, python_dependencies), "r"
                    ).readlines():
                        requirements_file.write(line)
                else:
                    for r in python_dependencies.split(","):
                        requirements_file.write(r + "\n")
            requirements_file.close()

        else:
            # Generate a generic 'run.sh' in src/ (no app)
            run_script = os.path.join(package_src_dir, "run.sh")
            with open(run_script, "w") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write('eval "$(ssh-agent -s)"\n')
                f.write(f"python -m ssf.cli $SSF_OPTIONS\n")
            st = os.stat(run_script)
            os.chmod(run_script, st.st_mode | stat.S_IEXEC)

        # Generate a 'build_image.sh' in /
        build_image_script = os.path.join(package_dir, "build_image.sh")
        build_command = "docker --debug --log-level debug build"
        with open(build_image_script, "w") as f:
            f.write("#!/usr/bin/env bash\n")
            f.write(
                f"stdbuf -oL -eL {build_command} --tag {package_tag} --file Dockerfile .\n"
            )

        st = os.stat(build_image_script)
        os.chmod(build_image_script, st.st_mode | stat.S_IEXEC)

        # Generate container image from template.
        logger.info(f"> Generate container image")
        src = os.path.join(ssf_dir, dockerfile_template_filename)
        dst = os.path.join(package_dir, "Dockerfile")

        symbol_parser = DockerFileSymbolParser(ssf_config)

        # Expand the template.
        expand_template(
            ssf_config,
            src,
            dst,
            [
                symbol_parser,
            ],
        )

        # Snapshot package.
        exit_code = logged_subprocess(
            "Tarball pack", ["tar", "-C", package_dir, "-czvf", package_name, "."]
        )
        if exit_code:
            raise SSFExceptionDockerBuildError(
                f"Tarball packing {package_dir} -> {package_name} errored ({exit_code})"
            )

        # Build container image.
        with temporary_cwd(package_dir):
            exit_code = logged_subprocess(
                f"Container image build {package_tag}", "./build_image.sh"
            )
            if exit_code:
                raise SSFExceptionDockerBuildError(
                    f"Build container image {package_tag} in {package_dir} errored ({exit_code})"
                )

        logger.info(f"> Package:")
        logger.info(f"> {package_name} (from {package_src_dir})")
        logger.info(f"> Test run: 'cd {package_src_dir} && ./run.sh'")

        logger.info("> Docker:")
        logger.info(
            f"> Run: 'docker run --rm -d --network host --name {application_id} {package_tag}'"
        )
        logger.info(
            f"> Run with IPU devices: 'gc-docker -- --rm -d  --name {application_id} {package_tag}'"
        )

        logger.info(f"> Logs: 'docker logs -f {application_id}'")
        logger.info(f"> Stop: 'docker stop {application_id}'")
    except Exception as e:
        raise SSFExceptionPackagingError(f"Failure packaging {application_id}.") from e

    return RESULT_OK
