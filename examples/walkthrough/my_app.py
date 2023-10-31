# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# --8<-- [start:imports]
from optimum.graphcore import pipeline
import logging
from ssf.application import SSFApplicationInterface
from ssf.utils import get_ipu_count
from ssf.results import RESULT_OK, RESULT_APPLICATION_ERROR

logger = logging.getLogger()
# --8<-- [end:imports]

# --8<-- [start:init]
class MyApplication(SSFApplicationInterface):
    def __init__(self):
        self.question_answerer: pipeline = None
        self.dummy_inputs_dict = {
            "question": "What is your name?",
            "context": "My name is Rob.",
        }

    # --8<-- [end:init]

    # --8<-- [start:build]
    def build(self) -> int:
        if get_ipu_count() >= 2:
            logger.info("Compiling model...")
            build_pipeline = pipeline(
                "question-answering", model="distilbert-base-cased-distilled-squad"
            )
            build_pipeline(self.dummy_inputs_dict)
        else:
            logger.info(
                "IPU requirements not met on this device, skipping compilation."
            )
        return RESULT_OK

    # --8<-- [end:build]

    # --8<-- [start:startup]
    def startup(self) -> int:
        logger.info("App started")
        self.question_answerer = pipeline(
            "question-answering", model="distilbert-base-cased-distilled-squad"
        )
        self.question_answerer(self.dummy_inputs_dict)
        return RESULT_OK

    # --8<-- [end:startup]
    # --8<-- [start:request]
    def request(self, params: dict, meta: dict) -> dict:
        result = self.question_answerer(params)
        return result

    # --8<-- [end:request]
    # --8<-- [start:shutdown]
    def shutdown(self) -> int:
        return RESULT_OK

    # --8<-- [end:shutdown]
    # --8<-- [start:watchdog]
    def watchdog(self) -> int:
        result = self.question_answerer(self.dummy_inputs_dict)
        return RESULT_OK if result["answer"] == "Rob" else RESULT_APPLICATION_ERROR

    # --8<-- [end:watchdog]
