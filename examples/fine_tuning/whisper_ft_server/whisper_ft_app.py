# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# Basic Whisper fine-tuning app for SSF based on optimum-graphcore/notebooks/whisper_finetuning.ipynb example
from pip_post_install import install
import logging
import json
from typing import Any, Tuple
from ft_interface import FineTuningInterface
from whisper_ft_utils import (
    LANGUAGE_DEFAULT,
    DATASET_DEFAULT,
    MODEL_NAME,
    MAX_LENGTH,
    TASK,
)
from whisper_ft_utils import (
    DataCollatorSpeechSeq2SeqWithLabelProcessing,
    MyProgressCallback,
)
from whisper_ft_utils import compute_metrics, get_model, get_ipu_config, get_datasets
from optimum.graphcore import (
    IPUSeq2SeqTrainer,
    IPUSeq2SeqTrainingArguments,
)
from optimum.graphcore.models.whisper import WhisperProcessorTorch
from ssf.utils import get_ipu_count
from ssf.results import *
from ssf.application import SSFApplicationTestInterface

logger = logging.getLogger("Fintetuning")


class WhisperFTApplication(FineTuningInterface):
    def __init__(self):
        self.language = LANGUAGE_DEFAULT
        self.checkpoints_dir = "./whisper-small-ipu-checkpoints"
        self.user_parameters_default = {
            "epochs": 1,
            "learning_rate": 1e-5,
            "warmup_ratio": 0.25,
            "dataset": DATASET_DEFAULT,
            "language": LANGUAGE_DEFAULT,
        }
        self.replication_factor = get_ipu_count() // 4
        self.ipu_config = get_ipu_config(self.replication_factor)
        self.processor = None
        self.trainer = None

    def load_user_json(self, params: dict) -> dict:
        try:
            user_dict = json.loads(params.get("parameters", ""))
        except Exception as e:
            user_dict = {}
            logger.info("No user parameter loaded")
            logger.warning(e)

        return user_dict

    def is_stub(self, params: dict) -> bool:
        # Check if the special key for testing is present
        user_dict = self.load_user_json(params)
        stub = user_dict.get("stub", False)
        return bool(stub)

    def init_dataset_and_processor(self, params: dict):
        logger.info("Loading dataset started")
        user_dict = self.load_user_json(params)

        hf_name = user_dict.get("dataset", self.user_parameters_default["dataset"])
        lang = user_dict.get("language", self.user_parameters_default["language"])

        self.language = lang
        self.processor = WhisperProcessorTorch.from_pretrained(
            MODEL_NAME, language=lang, task=TASK
        )
        self.processor.tokenizer.pad_token = self.processor.tokenizer.eos_token
        self.processor.tokenizer.max_length = MAX_LENGTH
        self.processor.tokenizer.set_prefix_tokens(language=lang, task=TASK)
        return get_datasets(self.processor, name=hf_name, language=lang), hf_name, lang

    def get_trainer(
        self, params: dict, logs_dict: dict, train_dataset: Any, eval_dataset: Any
    ):
        # Return a new trainer object with a pretrained model and clean state

        # init model
        model = get_model(self.processor, self.language)
        training_args_dict = {}
        logger.info(params)
        user_dict = self.load_user_json(params)
        epochs = user_dict.get("epochs", self.user_parameters_default["epochs"])
        initial_lr = user_dict.get(
            "learning_rate", self.user_parameters_default["learning_rate"]
        )
        warmup = user_dict.get(
            "warmup_ratio", self.user_parameters_default["warmup_ratio"]
        )

        training_args_dict.update(
            {
                # overwritable parameters
                "num_train_epochs": epochs,
                "learning_rate": initial_lr * self.replication_factor,
                "warmup_ratio": warmup,
                # frozen parameters
                "do_train": train_dataset is not None,
                "do_eval": eval_dataset is not None,
                "evaluation_strategy": "no",
                "output_dir": self.checkpoints_dir,
                "max_steps": 0,
                "eval_steps": 0,
                "predict_with_generate": True,
                "save_strategy": "epoch",
                "save_total_limit": 1,
                "logging_steps": 1,
                "dataloader_num_workers": 16,
                "dataloader_drop_last": True,
            }
        )

        logger.info(f"All args: {training_args_dict}")
        training_args = IPUSeq2SeqTrainingArguments(**training_args_dict)
        trainer = IPUSeq2SeqTrainer(
            model=model,
            ipu_config=self.ipu_config,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            data_collator=DataCollatorSpeechSeq2SeqWithLabelProcessing(self.processor),
            compute_metrics=lambda x: compute_metrics(x, self.processor.tokenizer),
            tokenizer=self.processor.feature_extractor,
            callbacks=[MyProgressCallback(logs_dict)],
        )
        return trainer

    def train(
        self, params: dict, train_dataset: Any, eval_dataset: Any, logs_dict: dict
    ) -> None:
        # Implement the "train" task (asynchronous) routine:
        # Training routine run for fine-tuning
        # Any metric/state can be saved by adding a (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        # see FineTuningInterface for more information

        # for testing
        if self.is_stub(params):
            return

        # we create a new trainer each time as we choose to re-tune each time
        trainer = self.get_trainer(
            params=params,
            logs_dict=logs_dict,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
        )
        trainer.train()
        # save trainer for future inference or saving
        self.trainer = trainer

    def eval(self, params: dict, eval_dataset: Any, logs_dict: dict) -> None:
        # Implement the "eval" task (asynchronous) routine:
        # Evaluation routine
        # Any metric can be saved by adding (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        # see FineTuningInterface for more information

        # for testing
        if self.is_stub(params):
            return

        if self.trainer is not None:
            self.trainer.evaluate()
        else:
            logger.warning("Model was not fine-tuned")
            trainer = self.get_trainer(
                params=params,
                logs_dict=logs_dict,
                train_dataset=None,
                eval_dataset=eval_dataset,
            )
            trainer.evaluate()

    def dataset(self, params: dict, logs_dict: dict) -> tuple:
        # Implement the "dataset" task (asynchronous) routine:
        # Download/prepare the datasets used in "train" and "eval" routines
        # Any metric can be saved by adding (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        # returns: (train_dataset, eval_dataset)
        # see FineTuningInterface for more information

        # for testing
        if self.is_stub(params):
            return ([], [])

        (train_ds, eval_ds), name, lang = self.init_dataset_and_processor(params)
        logger.info("Dataset loaded successfully")
        logs_dict["dataset"] = name + ":" + lang
        return (train_ds, eval_ds)

    def test(self, params: dict, logs_dict: dict) -> None:
        # Implement the "test" task (synchronous) routine:
        # Can receive custom inputs to test the model accuracy
        # Any metric can be saved by adding (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        # see FineTuningInterface for more information
        logger.info("Not implemented")

    def save(self, params: dict, logs_dict: dict) -> None:
        # Implement the "save" task: Any code to retrieve/upload the model
        # weights/checkpoint.
        # Any metric can be saved by adding (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        # see FineTuningInterface for more information

        # for testing
        if self.is_stub(params):
            return

        if self.trainer is not None:
            self.trainer.model.deparallelize()
            self.trainer.model.push_to_hub("whisper-small-ft-example")

    def status(self, status_msg: str, params: dict, logs_dict: dict) -> str:
        # Implement the "status" task: This returns a status message.

        # parameters:
        #   status_msg:  String containing the app status message.
        #       (Ready, Busy training/evaluating, Training started, Evaluation started)

        #   params: users input dict declared in SSF config
        #   logs_dict: Any metric added in the other methods can be retrieved from `logs_dict`.

        # returns:
        #   String: Status message message.
        progress = 0
        steps = [logs_dict.get("step", None), logs_dict.get("total_step", None)]
        if not any([s is None for s in steps]):
            progress = 100 * steps[0] / steps[1]

        full_status = str(
            {
                "train_progress_%": float(progress),
                "dataset": logs_dict.get("dataset", "Not set"),
                "train_epoch": logs_dict.get("epoch", 0),
                "lr": logs_dict.get("learning_rate", 0),
                "loss": logs_dict.get("current_loss", 0),
                "eval_WER": logs_dict.get("eval_wer", 0),
            }
        )
        return full_status


def create_ssf_application_instance():
    return WhisperFTApplication()


# For internal testing
class WhisperFTApplicationTest(SSFApplicationTestInterface):
    def begin(self, session, ipaddr: str) -> int:
        logger.info("MyApp test begin")
        return RESULT_OK

    def subtest(self, session, ipaddr: str, index: int) -> Tuple[bool, str, bool]:

        url = f"{ipaddr}/v1/finetuning/"
        params = {"task": None, "parameters": '{"stub" : true}'}

        def test_request(task: str, expected_state: str) -> Tuple[bool, str]:
            params["task"] = task
            response = session.post(
                url, json=params, headers={"accept": "application/json"}, timeout=5
            )
            response_str = "Test failed"
            if response.status_code == 200:
                response_str = response.json()["response"]
                if expected_state in response_str:
                    return (True, "Test passed")

            return (False, response_str)

        test_entries = {
            0: ("train", "Error: Cannot start training"),
            1: ("eval", "Error: Cannot start evaluating"),
            2: ("dataset", "Dataset processing Started"),
            3: ("train", "Training Started"),
            4: ("eval", "Eval Started"),
            5: ("status", "Status"),
            6: ("status", "Ready"),
            7: ("save", "Ready"),
        }

        test_tuple = test_entries[index]
        status, message = test_request(test_tuple[0], test_tuple[1])
        if index == len(test_entries) - 1:
            # stop testing
            return (status, message, False)
        else:
            # continue testing
            return (status, message, True)

    def end(self, session, ipaddr: str) -> int:
        logger.info("MyApp test end")
        return RESULT_OK


def create_ssf_application_test_instance(ssf_config) -> SSFApplicationTestInterface:
    logger.info("Create MyApplication test instance")
    return WhisperFTApplicationTest()
