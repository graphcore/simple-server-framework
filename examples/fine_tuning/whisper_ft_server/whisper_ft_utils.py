# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import evaluate
from dataclasses import dataclass
import numpy as np
import torch
from datasets import load_dataset, Audio, Dataset, DatasetDict
from typing import Any, Dict, List, Union, Tuple
from transformers import WhisperForConditionalGeneration, TrainerCallback
from optimum.graphcore import IPUConfig


MODEL_NAME = "openai/whisper-small"
LANGUAGE_DEFAULT = "as"
DATASET_DEFAULT = "mozilla-foundation/common_voice_13_0"
TASK = "transcribe"
MAX_LENGTH = 224


def get_ipu_config(replication_factor: int) -> IPUConfig:
    return IPUConfig.from_dict(
        {
            "optimizer_state_offchip": True,
            "recompute_checkpoint_every_layer": True,
            "enable_half_partials": True,
            "executable_cache_dir": "./whisper_exe_cache",
            "gradient_accumulation_steps": 16,
            "replication_factor": replication_factor,
            "layers_per_ipu": [5, 7, 5, 7],
            "matmul_proportion": [0.2, 0.2, 0.6, 0.6],
            "projection_serialization_factor": 5,
            "inference_replication_factor": 1,
            "inference_layers_per_ipu": [12, 12],
            "inference_parallelize_kwargs": {
                "use_cache": True,
                "use_encoder_output_buffer": True,
                "on_device_generation_steps": 16,
            },
        }
    )


def prepare_dataset(batch: dict, processor: Any) -> dict:
    inputs = processor.feature_extractor(
        raw_speech=batch["audio"]["array"],
        sampling_rate=batch["audio"]["sampling_rate"],
    )
    batch["input_features"] = inputs.input_features[0].astype(np.float16)
    transcription = batch["sentence"]
    batch["labels"] = processor.tokenizer(text=transcription).input_ids
    return batch


def get_datasets(
    processor: Any, name: str, language: str
) -> Tuple[DatasetDict, DatasetDict]:
    dataset = DatasetDict()
    try:
        split_dataset = Dataset.train_test_split(
            load_dataset(
                name,
                language,
                split="train",
                use_auth_token=True,
            ),
            test_size=0.2,
            seed=0,
        )
    except Exception as e:
        # User may not be logged, catch it early
        raise e
    dataset["train"] = split_dataset["train"]
    dataset["eval"] = split_dataset["test"]
    dataset = dataset.remove_columns(["path"])
    # Processing:
    dataset = dataset.cast_column("audio", Audio(sampling_rate=16000))
    columns_to_remove = dataset.column_names["train"]
    dataset = dataset.map(
        lambda elem: prepare_dataset(elem, processor),
        remove_columns=columns_to_remove,
        num_proc=1,
    )

    train_dataset = dataset["train"]
    eval_dataset = dataset["eval"]
    return train_dataset, eval_dataset


@dataclass
class DataCollatorSpeechSeq2SeqWithLabelProcessing:
    processor: Any

    def __call__(
        self, features: List[Dict[str, Union[List[int], torch.Tensor]]]
    ) -> Dict[str, torch.Tensor]:
        batch = {}
        batch["input_features"] = torch.tensor(
            [feature["input_features"] for feature in features]
        )
        label_features = [{"input_ids": feature["labels"]} for feature in features]
        labels_batch = self.processor.tokenizer.pad(
            label_features,
            return_tensors="pt",
            padding="longest",
            pad_to_multiple_of=MAX_LENGTH,
        )
        labels = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1), -100
        )
        batch["labels"] = labels
        return batch


def compute_metrics(pred: Any, tokenizer: Any) -> Dict[str, float]:
    metric = evaluate.load("wer")
    pred_ids = pred.predictions
    label_ids = pred.label_ids

    # replace -100 with the pad_token_id
    pred_ids = np.where(pred_ids != -100, pred_ids, tokenizer.pad_token_id)
    label_ids = np.where(label_ids != -100, label_ids, tokenizer.pad_token_id)

    pred_str = tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
    label_str = tokenizer.batch_decode(label_ids, skip_special_tokens=True)

    normalized_pred_str = [tokenizer._normalize(pred).strip() for pred in pred_str]
    normalized_label_str = [tokenizer._normalize(label).strip() for label in label_str]

    wer = 100 * metric.compute(predictions=pred_str, references=label_str)
    normalized_wer = 100 * metric.compute(
        predictions=normalized_pred_str, references=normalized_label_str
    )

    return {"wer": wer, "normalized_wer": normalized_wer}


def get_model(processor: Any, language: str):
    model = WhisperForConditionalGeneration.from_pretrained(MODEL_NAME)
    model.config.max_length = MAX_LENGTH
    model.generation_config.max_length = MAX_LENGTH
    model.config.forced_decoder_ids = processor.tokenizer.get_decoder_prompt_ids(
        language=language, task=TASK
    )
    model.config.suppress_tokens = []
    model.generation_config.forced_decoder_ids = (
        processor.tokenizer.get_decoder_prompt_ids(language=language, task=TASK)
    )
    model.generation_config.suppress_tokens = []
    return model


class MyProgressCallback(TrainerCallback):
    "A callback that records progress and metrics into a dict"

    def __init__(self, state_dict) -> None:
        state_dict["current_loss"] = 0
        state_dict["learning_rate"] = 0
        state_dict["epoch"] = 0
        state_dict["step"] = 0
        state_dict["eval_wer"] = 0
        state_dict["total_step"] = None
        self.state_dict = state_dict

    def on_train_begin(self, args, state, control, **kwargs) -> None:
        self.state_dict["eval_wer"] = 0

    def on_step_end(self, args, state, control, **kwargs) -> None:
        self.state_dict["step"] = state.global_step
        self.state_dict["total_step"] = state.max_steps

    def on_log(self, args, state, control, logs=None, **kwargs) -> None:
        self.state_dict["current_loss"] = logs.get(
            "loss", self.state_dict["current_loss"]
        )
        self.state_dict["learning_rate"] = logs.get(
            "learning_rate", self.state_dict["learning_rate"]
        )
        self.state_dict["epoch"] = logs.get("epoch", self.state_dict["epoch"])

    def on_evaluate(self, args, state, control, metrics, **kwargs) -> None:
        self.state_dict["eval_wer"] = metrics.get("eval_wer")
