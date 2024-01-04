# Whisper-small fine tuning example

This example shows how to implement a simple fine-tuning "worker" microservice with SSF.
It is made to handle one fine-tuning job at a time and provide features such as evaluating, returning metrics, testing and saving.


- config.yaml : SSF config file
- whisper_ft_app.py : Main SSF APP implementation
- whisper_ft_utils.py : Utility functions for whisper finetuning
- ft_interface.py : Contains the FineTuningInterface class, used to define an interface for a fine-tuning server.  
  This interface can be reused for other fine-tuning projects.

# Licensing

This example uses libraries from Hugging Face and the Whisper-small model from OpenAI.

## Hugging Face

Apache License, Version 2.0

https://github.com/huggingface/transformers/blob/main/LICENSE

Apache License, Version 2.0

https://github.com/huggingface/optimum-graphcore/blob/main/LICENSE

## Whisper-small model (Hugging Face)

Apache License, Version 2.0

https://huggingface.co/openai/whisper-small/tree/main

# Instructions and limitations

Just use SSF normally to run/deploy this example.\

- This example uses Hugging Face Hub features. To use this example you will either need to be logged in with the Hugging Face CLI or have set set the environment variable `HUGGING_FACE_HUB_TOKEN`.
- This example does not support gRPC (do not use it with `--api grpc`)
- This example does not support replication (do not use `--replicate-application` or `--replicate-server`)


# API
The main app `WhisperFTApplication` inherits from `FineTuningInterface` which defines a specific API.

This interface allows you to build a single endpoint relying on one input parameter and one output parameter: `task`(input) and `response`(output).
They must be defined in the SSF config file `config.yaml`:

```yaml
endpoints:
  - id: finetuning
    version: 1
    desc: Fine-tune whisper small
    inputs:
      - id: task
        type: String
        desc: |
          One of the following tasks {"dataset", "train", "eval", "test", "save", "status"}.
          (Not executed if status is "Busy")
          Usage:
            dataset: process the dataset
            train : start finetuning job
            eval : start eval job
            test : test the model
            save : upload model checkpoint to Hugging Face Hub
            status : return status string

    outputs:
      - id: response
        type: String
        desc: Fine-tuning server response string.
```
The API defines these 5 tasks that can be called via the String input `task`

- dataset (async) : implemented by the method `dataset` - job to initialise the train and eval dataset
- train (async) : implemented by the method `train` - job to fine tune the model
- eval (async) : implemented by the method `eval` - job to evaluate the model
- test (sync) : implemented by the method `test` - job to test the model on custom inputs
- save (sync) : implemented by the method `save` - job to save the model
- status (sync): implemented by the method `status` - job to make a custom status string that will be added to the response

For any task called, the output `response` will contain an `Internal state` field giving information on the current service state, for instance:
`Ready`, `Busy Training/Evaluating`, `Started training`, `Error:...`
Example response body:
```json
{
  "Response": "{'Internal state': 'Ready'}"
}
```
When the task `status` is called, the custom status string (if any defined) is also appended to the response in the field `Status`.
Example response body with `status`:
```json
{
  "Response": "{'Internal state': 'Busy training', 'Status': \"{'train_progress_%': 0.0, 'dataset': 'mozilla-foundation/common_voice_13_0:as', 'train_epoch': 0, 'lr': 0, 'loss': 0, 'eval_WER': 0}\"}"
}
```
When an async task is requested, the server will ignore the following request until completion, without blocking.
The `response` will always be returned, it contains an `Internal state` field that will indicate `Busy` until the task finished.

### Note:

For the example `WhisperFTApplication` we used another `String` input called `arguments` that can be used to pass optional arguments to the app as a JSON string.
These arguments and their default values are the following:

```json
{
    "epochs": 1,
    "learning_rate": 1e-5,
    "warmup_ratio": 0.25,
    "dataset": "mozilla-foundation/common_voice_13_0",
    "language": "as"
}
```


# FineTuningInterface usage

The class `FineTuningInterface` is a child class of `SSFApplicationInterface`. It defines a generic fine-tuning API and it comes with a pre-implemented behaviour.
The following abstract methods are left to the user app class to implement when inheriting:

```python
@abstractmethod
def train(self, params: dict, train_dataset: Any, eval_dataset: Any, logs_dict: dict) -> None:
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
    #   String: Status message.
    pass
```

### States:

`FineTuningInterface` keeps internal states:
-  The eval and train datasets are part of the internal state.\
-> The `dataset` task must be called before `train` or `eval` task to initialises the datasets.
Otherwise the tasks will be ignored and the error will be written in `status_msg`

- A dictionary (passed as `logs_dict` in all the previous methods) is part of the state. It can be used to keep track of some metrics during task execution and key-values can be returned in the method `response`.



# API usage example (whisper_ft_app.py):


1 - Request body to setup the dataset common_voice_13_0 Assamese.

```json
{
  "task": "dataset",
  "parameters": "{\"dataset\": \"mozilla-foundation/common_voice_13_0\", \"language\": \"as\"}"
}
```
response body:

```json
{
  "response": "{'Internal state': 'Dataset processing Started'}",
}
```

-> `Internal state` will indicate busy on any subsequent requests until completion, for instance:
```json
{
  "response": "{'Internal state': 'Busy processing dataset'}"
}
```

2 - Request body to fine-tune on 10 epochs:
```json
{
  "task": "train",
  "parameters": "{\"epochs\": 10}"
}
```
response body:
```json
{
  "response": "{'Internal state': 'Training Started'}"
}
```
-> `Internal state` will indicate busy on any subsequent requests until completion.\
For instance:
```json
{
  "response": "{'Internal state': 'Busy training'}"
}
```
Note: The model will take time to compile the very first time you run it, but it will be cached (`./whisper_exe_cache`) and will not recompile the next time.

3 - Request body to get the status message.
```json
{
  "task": "status",
  "parameters": {}
}
```
This will return our custom status message (with the training metrics), for example:
Status request, response body example:
```json
{
  "response": "{'Internal state': 'Busy training', 'Status': \"{'train_progress_%': 50.0, 'dataset': 'mozilla-foundation/common_voice_13_0:as', 'train_epoch': 1.0, 'lr': 2.8e-05, 'loss': 1.9102, 'eval_WER': 0}\"}"
}
```
3 - Request body to run the eval.
```json
{
  "task": "eval",
  "parameters": {}
}
```
-> Again, `Internal state` will indicate busy on any subsequent requests until completion.\
-> when finished the obtained `eval_WER` will be returned by the `status` task.
(Note: Launching a new  `train` task will restart fine-tuning from a fresh model checkpoint and overwrite all these metrics)


## Note on the example design:
When implementing the Whisper example, some choice were made to keep the app simple.\
(None of these are enforced by the `FineTuningInterface`)

In this example the `WhisperFTApplication` instance keeps a `trainer` object as an internal state:
The `trainer` object contains the model and all its associated training state.

Only one model is kept at a time:\
When the API calls `train`, any previous `trainer` and associated model are discarded. A new trainer and model are instanciated and fine-tuned.\

When the API calls `eval`, the model used for eval is the fine-tuned model. If `train` wasn't called yet, a new trainer is instanciated and the evaluation runs on the model with its initial weights. This way, we can compare the evaluation score before and after fine-tuning.\

When the API calls `save`, the model checkpoint is pushed to Hugging Face Hub. The machine needs to be authentificated via huggingface CLI to do so. If no model was fine-tuned nothing happens.
