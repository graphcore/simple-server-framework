# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import requests
import io
import imghdr
import os
from typing import Tuple
import tempfile

from ssf.application_interface.application import (
    SSFApplicationInterface,
    SSFApplicationTestInterface,
)
from ssf.application_interface.utils import get_ipu_count
from ssf.application_interface.results import *

logger = logging.getLogger("SD2")


def check_available_ipus(req_ipus: int) -> bool:
    return get_ipu_count() >= req_ipus


def compile_or_load_model_exe(pipe, seed_generator):
    try:
        pipe(
            prompt="Big red dog",
            height=512,
            width=512,
            generator=seed_generator(31337),
            guidance_scale=9,
            num_inference_steps=1,
        )
    except Exception as e:
        logger.error(f"Model compile/load step failed with {e}.")
        return RESULT_FAIL

    return RESULT_OK


class StableDiffusion2API(SSFApplicationInterface):
    def __init__(self):
        import torch
        from optimum.graphcore.diffusers import IPUStableDiffusionPipeline
        from diffusers import DPMSolverMultistepScheduler

        self._pipe = None

        min_ipus = 4  # Minimum IPUs needed to run this example (specified in config)
        max_ipus = (
            8  # Max IPUs to run 'high performance' version, will run if available.
        )

        # Check for IPUs here in init, to prep required IPU configs.
        self.req_ipus = max_ipus
        if not check_available_ipus(max_ipus):
            logger.warning(
                f"{max_ipus} IPUs not available. Stable Diffusion 2 will default to 4-IPU version! Trying {min_ipus} IPUs..."
            )
            self.req_ipus = min_ipus
            if not check_available_ipus(min_ipus):
                raise SSFExceptionUnmetRequirement(f"{min_ipus} IPUs not available. ")

        self._pipe = IPUStableDiffusionPipeline.from_pretrained(
            "stabilityai/stable-diffusion-2-1-base",
            revision="fp16",
            torch_dtype=torch.float16,
            requires_safety_checker=False,
            n_ipu=self.req_ipus,
        )

        self._pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            self._pipe.scheduler.config
        )

        self._pipe.enable_attention_slicing()

        self.seed_gen = torch.manual_seed

    def build(self) -> int:
        logger.info(f"Stable Diffusion 2 API build - compile to generate executable")

        if not check_available_ipus(self.req_ipus):
            raise SSFExceptionUnmetRequirement(f"{self.req_ipus} IPUs not available.")

        logger.info(f"{self.req_ipus} IPUs available for model. Building...")
        return compile_or_load_model_exe(self._pipe, self.seed_gen)

    def startup(self) -> int:
        logger.info("Stable Diffusion 2 API startup - trigger load executable")

        if not check_available_ipus(self.req_ipus):
            raise SSFExceptionUnmetRequirement(f"{self.req_ipus} IPUs not available.")

        logger.info(f"{self.req_ipus} IPUs available for model. Loading...")
        return compile_or_load_model_exe(self._pipe, self.seed_gen)

    def request(self, params: dict, meta: dict) -> dict:
        logger.info(f"Stable Diffusion 2 API request with params={params} meta={meta}")

        result = self._pipe(
            prompt=params["prompt"],
            height=512,
            width=512,
            guidance_scale=params["guidance_scale"],
            num_inference_steps=params["num_inference_steps"],
            generator=self.seed_gen(params["random_seed"]),
            negative_prompt=params["negative_prompt"],
        )

        # single image support only for now
        image = result["images"][0]
        image_binary = io.BytesIO()
        image.save(image_binary, format="PNG")

        result_dict = {"result": image_binary.getvalue()}

        logger.info(
            f"Stable Diffusion 2 API returning result='result':<base64 encoded image>"
        )
        logger.debug(f"Full return response: {result_dict}")

        return result_dict

    def shutdown(self) -> int:
        logger.info("Stable Diffusion 2 API shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("Stable Diffusion 2 API watchdog")
        return RESULT_OK


# NOTE:
# This can be called multiple times (with separate processes)
# if running with multiple workers (replicas). Be careful that
# your application can handle multiple parallel worker processes.
# (for example, that there is no conflict for file I/O).
def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("Create Stable Diffusion 2 API instance")
    return StableDiffusion2API()


class MyApplicationTest(SSFApplicationTestInterface):
    def begin(self, session, ipaddr: str) -> int:
        logger.info("MyApp test begin")
        return RESULT_OK

    def subtest(self, session, ipaddr: str, index: int) -> Tuple[bool, str, bool]:

        # Check for IPUs available for test, this affects the generated output image.
        # Default set to 8 here to keep consistency with application.
        req_ipus = 8
        if not check_available_ipus(req_ipus):
            req_ipus = 4
            if not check_available_ipus(req_ipus):
                return (False, f"Test failure: {req_ipus} IPUs not available.", False)

        logger.info(f"Running SD2 test with {req_ipus} IPUs version.")

        version = 1
        subtests = 1
        last_index = subtests - 1
        endpoint_name = "txt2img_512"

        test_input = {
            "prompt": "A large bottle of shiny blue juice",
            "guidance_scale": 9,
            "num_inference_steps": 25,
            "negative_prompt": "red",
            "random_seed": 5555,
        }

        logger.debug(
            f"MyApp test index={index} ver={version} test_input={test_input} test_expected= 'png' type image"
        )

        try:
            url = f"{ipaddr}/v{version}/{endpoint_name}"
            params = test_input

            logger.info(f"POST with params={params}")

            # Needs a long timeout as first request downloads model + loads executable.
            response = session.post(
                url, json=params, headers={"accept": "*/*"}, timeout=2700
            )

            MAGIC1 = 200
            MAGIC2 = "png"

            # Check staus code
            ok_1 = response.status_code == MAGIC1
            if not ok_1:
                logger.error(
                    f"Failed {url} with {params} : {response.status_code} v expected {MAGIC1}"
                )
            else:
                logger.info(
                    f"SD2 passed subtest check 1: expected {MAGIC1} v received {response.status_code}"
                )

            # Verify output binary value image type
            out_type = None
            try:
                # Write response to an undefined binary filetype
                with tempfile.NamedTemporaryFile(mode="wb+") as tmp:
                    tmp.write(response.content)

                    # Use Python built-in imghdr module to check type, expect 'png'
                    out_type = imghdr.what(tmp.name)

                    # Verify type
                    ok_2 = out_type == MAGIC2

            except Exception as e:
                ok_2 = False
                logger.error(f"Error with test temporary file creation/deletion: {e}")

            if not ok_2:
                logger.error(
                    f"Failed {url} with {params} : {response.content[:100]} is of type {out_type} v expected type PNG"
                )
            else:
                logger.info(
                    f"SD2 passed subtest check 2: expected {MAGIC2} v received '{out_type}'"
                )

            return (
                ok_1 == ok_2 == True,
                f"v{version} {test_input} => image type {out_type}",
                index < last_index,
            )

        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return (False, e, False)

    def end(self, session, ipaddr: str) -> int:
        logger.info("MyApp test end")
        return RESULT_OK


def create_ssf_application_test_instance(ssf_config) -> SSFApplicationTestInterface:
    logger.info("Create MyApplication test instance")
    return MyApplicationTest()
