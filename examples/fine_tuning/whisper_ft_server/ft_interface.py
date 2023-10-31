# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
from ssf.application import SSFApplicationInterface
from ssf.results import RESULT_OK
from typing import Any
import threading as th
import multiprocessing as mp
from abc import abstractmethod

logger = logging.getLogger("Fintetuning")


class FineTuningInterface(SSFApplicationInterface):
    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls, *args, **kwargs)
        instance._is_training = th.Event()
        instance._is_eval = th.Event()
        instance._is_dataset = th.Event()
        instance._thread_error = th.Event()
        instance._trainer_thread: th.Thread = None
        instance._eval_thread: th.Thread = None
        instance._dataset_thread: th.Thread = None
        instance._state: dict = {}
        instance._train_dataset = None
        instance._eval_dataset = None
        return instance

    @abstractmethod
    def train(
        self,
        params: dict,
        train_dataset: Any,
        eval_dataset: Any,
        logs_dict: dict,
    ) -> None:
        # Implement the "train" task (asynchronous) routine:
        # Training routine run for fine-tuning

        # Any metric/state can be saved by adding a (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        pass

    @abstractmethod
    def eval(self, params: dict, eval_dataset: Any, logs_dict: dict) -> None:
        # Implement the "eval" task (asynchronous) routine:
        # Evaluation routine

        # Any metric can be saved by adding (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        pass

    @abstractmethod
    def dataset(self, params: dict, logs_dict: dict) -> tuple:
        # Implement the "dataset" task (asynchronous) routine:
        # Download/prepare the datasets used in "train" and "eval" routines

        # Any metric can be saved by adding (key,value) in `logs_dict`
        # and retrieved in the `status` method.

        # returns: (train_dataset, eval_dataset)
        pass

    @abstractmethod
    def test(self, params: dict, logs_dict: dict) -> None:
        # Implement the "test" task (synchronous) routine:
        # Can receive custom inputs to test the model accuracy

        # Any metric can be saved by adding (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        pass

    @abstractmethod
    def save(self, params: dict, logs_dict: dict) -> None:
        # Implement the "save" task: Any code to retrieve/upload the model
        # weights/checkpoint.

        # Any metric can be saved by adding (key,value) in `logs_dict`
        # and retrieved in the `status` method.
        pass

    @abstractmethod
    def status(self, status_msg: str, params: dict, logs_dict: dict) -> str:
        # Implement the "status" task: This returns a status message.

        # parameters:
        #   status_msg:  String containing the app status message.
        #       (Ready, Busy training/evaluating, Training started, Evaluation started)

        #   params: users input dict declared in SSF config
        #   logs_dict: Any metric added in the other methods can be retrieved from `logs_dict`.

        # returns:
        #   String: Status message message.
        pass

    def response(self, status_msg: str, user_status: str = None) -> str:
        response = {
            "Internal state": status_msg,
        }
        if user_status is not None:
            response.update(
                {
                    "Status": str(user_status),
                }
            )
        return {"response": str(response)}

    def thread_routine(self, params: dict, busy: th.Event, task: str) -> None:
        busy.set()
        mp.set_start_method("fork", force=True)
        self._thread_error.clear()
        try:
            if task == "train":
                self.train(params, self._train_dataset, self._eval_dataset, self._state)
            if task == "eval":
                self.eval(params, self._eval_dataset, self._state)
            if task == "dataset":
                self._train_dataset, self._eval_dataset = self.dataset(
                    params, self._state
                )
        except BaseException as e:
            self._thread_error.set()
            raise e
        finally:
            busy.clear()
        return

    def request(self, params: dict, meta: dict) -> dict:
        busy = (
            self._is_training.is_set()
            or self._is_eval.is_set()
            or self._is_dataset.is_set()
        )
        status_msg = "Ready"
        user_status = None

        if busy:
            if self._is_training.is_set():
                job = "training"
            elif self._is_eval.is_set():
                job = "evaluating"
            else:
                job = "processing dataset"
            status_msg = "Busy " + job

        else:
            if "dataset" in params["task"]:
                self._dataset_thread = th.Thread(
                    target=self.thread_routine,
                    args=(
                        params,
                        self._is_dataset,
                        "dataset",
                    ),
                )
                self._dataset_thread.start()
                status_msg = "Dataset processing Started"

            if params["task"] == "train":
                if self._train_dataset is None:
                    status_msg = "Error: Cannot start training, use task 'dataset' first to initialise the dataset"
                    logger.error(status_msg)
                else:
                    self._trainer_thread = th.Thread(
                        target=self.thread_routine,
                        args=(
                            params,
                            self._is_training,
                            "train",
                        ),
                    )
                    self._trainer_thread.start()
                    status_msg = "Training Started"

            if params["task"] == "eval":
                if self._eval_dataset is None:
                    status_msg = "Error: Cannot start evaluating, use task 'dataset' first to initialise the dataset"
                    logger.error(status_msg)
                else:
                    logger.info("Evaluating")
                    self._eval_thread = th.Thread(
                        target=self.thread_routine,
                        args=(
                            params,
                            self._is_eval,
                            "eval",
                        ),
                    )
                    self._eval_thread.start()
                    status_msg = "Eval Started"

            if params["task"] == "test":
                logger.info("Testing")
                self.test(params, self._state)

            if params["task"] == "save":
                logger.info("Saving")
                self.save(params, self._state)

        if self._thread_error.is_set():
            status_msg = "Error detected, last async task failed"

        if params["task"] == "status":
            user_status = self.status(status_msg, params, self._state)
        result = self.response(status_msg, user_status)
        return result

    def build(self) -> int:
        return RESULT_OK

    def startup(self) -> int:
        return RESULT_OK

    def shutdown(self) -> int:
        return RESULT_OK

    def watchdog(self) -> bool:
        return RESULT_OK
