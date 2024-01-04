# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from datetime import datetime
import logging
import os
import typing
from typing import Any

from ssf.application_interface.config import SSFConfig, EndpointDescription
from ssf.application_interface.results import *

from ssf.fastapi_runtime.fastapi_types import handler, gen_output_type_mapping, handlers
from ssf.utils import lookup_dict, API_FASTAPI
from ssf.template import TemplateSymbolParser, expand_template


logger = logging.getLogger("ssf")


API_INPUT_FORMATS = ["json", "query"]

# Examples for query API
# x: int= Query(example=99),
# y: int= Query(example=32322),


def get_input_format(inputs, default=None):
    # User flexibility only applies when sending no custom parameters (json/query), if any custom parameters
    # are involved, default is query. If only custom parameters are passed, it doesn't matter, as the POST request
    # is done through `files=` regardless.

    # If there are no generic type params, the input format doesn't matter but should be set to query here
    # to avoid JSON param behaviour in parser

    # Check presence of any custom inputs
    custom = False
    for param in inputs:
        if param.dtype in handlers["custom"]:
            custom = True
            break

    # If any generic inputs are set together with custom inputs, input format is *always* query.
    if custom:
        return "query"

    # If no custom params, default to JSON or user defined format.
    else:
        if default not in API_INPUT_FORMATS:
            if default is not None:
                logger.warning(
                    f"{default} not an allowed input format. Must be one of {API_INPUT_FORMATS}, defaulting to 'json'."
                )
            return "json"
        else:
            return default


def generate(ssf_config: SSFConfig, idx: int, application_endpoint: str):
    api = ssf_config.args.api

    if not api == API_FASTAPI:
        raise SSFExceptionInternalError(f"Unexpected api {api}")

    endpoint = ssf_config.endpoints[idx]

    inputs = endpoint.inputs
    outputs = endpoint.outputs

    for param in inputs:
        if (
            param.dtype not in handlers["generic"]
            and param.dtype not in handlers["custom"]
        ):
            raise SSFExceptionApplicationConfigError(f"Input with unknown type {param}")
    for param in outputs:
        if (
            param.dtype not in handlers["generic"]
            and param.dtype not in handlers["custom"]
        ):
            raise SSFExceptionApplicationConfigError(
                f"Output with unknown type {param}"
            )

    default = None
    if endpoint.http_param_format is not None:
        default = endpoint.http_param_format

    input_format = get_input_format(inputs, default)

    generate_path, _ = os.path.split(__file__)
    template_file = os.path.join(generate_path, f"{api}.template")

    logger.debug(
        f"Generating server with {api} end-points -> {application_endpoint} from template {template_file} with config {ssf_config}"
    )

    # Define a custom parser for the FastAPI template.
    class FastAPISymbolParser(TemplateSymbolParser):
        def __init__(self, ssf_config: SSFConfig, endpoint: EndpointDescription):
            self.ssf_config = ssf_config
            self.endpoint = endpoint

        def parse(self, symbol_id: str, indent: int = 0) -> str:
            if symbol_id.find("endpoint.") == 0:
                # Where symbols have syntax ".... {{endpoint.< >}} ...."
                # Will be replaced with lookup into the "endpoint." namespace.
                return lookup_dict(self.endpoint, symbol_id, namespaced=True)

            elif symbol_id == "inputs_as_base_model":
                # This converts the ssf_config input list to a FastAPI parameter list (one-per-line, comma-separated)
                parsed_inputs = []

                examples = []

                # If format is query - nothing is added to BaseModel for this symbol_id
                if input_format == "query":
                    return ""

                # If format is json - inputs are added to BaseModel expecting no inputs to be custom types.
                else:
                    for param in inputs:
                        if param.dtype in handlers["generic"]:
                            parsed_inputs.extend(
                                handler(param.dtype).gen_param(
                                    self.ssf_config, param, is_basemodel=True
                                )
                            )
                            if param.example is not None:
                                examples.extend(
                                    handler(param.dtype).gen_example(
                                        self.ssf_config, param
                                    )
                                )
                        else:
                            # This should ideally never be raised
                            raise SSFExceptionInternalError(
                                "Input format detected as JSON while containing non-JSONable params (e.g. TempFile). Use 'query'."
                            )

                if len(parsed_inputs) == 0:
                    raise SSFExceptionApplicationConfigError(f"Inputs empty")

                if len(examples) > 0:
                    parsed_inputs.extend(
                        [
                            "class Config:",
                            "  schema_extra = {",
                            "    'examples': [",
                            "       {" + ", ".join(examples) + "}",
                            "    ]",
                            "  }",
                        ]
                    )

                split_string = "\n" + " " * indent
                insert_lines = split_string.join(parsed_inputs)

                return insert_lines

            elif symbol_id == "inputs_as_params":
                base_model_set = False
                parsed_inputs = []

                if input_format == "json":
                    # Always the same, Pydantic BaseModel contains all inputs, custom inputs not passed in json format.
                    parsed_inputs.extend([f"inputs: Inputs"])

                if input_format == "query":
                    for param in inputs:
                        # If generic types, the parameter default is '=Query(...)' for query format
                        if param.dtype in handlers["generic"]:
                            parsed_inputs.extend(
                                handler(param.dtype).gen_param(
                                    self.ssf_config, param, is_basemodel=False
                                )
                            )

                        # if custom types, add custom parameters to endpoint args as normal
                        else:
                            parsed_inputs.extend(
                                handler(param.dtype).gen_param(self.ssf_config, param)
                            )

                split_string = ",\n" + " " * indent
                insert_lines = split_string.join(parsed_inputs)

                return insert_lines

            elif symbol_id == "inputs_as_doc_strings":
                # This converts the ssf_config input list to a doc parameter list (one-per-line)
                parsed_inputs = []
                for param in inputs:
                    parsed_inputs.extend(
                        handler(param.dtype).gen_docstring(self.ssf_config, param)
                    )

                split_string = "\n" + " " * indent
                insert_lines = split_string.join(parsed_inputs)
                return insert_lines

            elif symbol_id == "outputs_as_doc_strings":
                # This converts the ssf_config output list to a doc parameter list (one-per-line)
                parsed_inputs = []
                for param in outputs:
                    parsed_inputs.extend(
                        handler(param.dtype).gen_docstring(self.ssf_config, param)
                    )

                split_string = "\n" + " " * indent
                insert_lines = split_string.join(parsed_inputs)
                return insert_lines

            elif symbol_id == "preprocess":
                # This adds ssf type specific pre-processing (multiple lines)
                parsed_inputs = []
                for param in inputs:
                    parsed_inputs.extend(
                        handler(param.dtype).gen_preprocess(self.ssf_config, param)
                    )

                split_string = "\n" + " " * indent
                insert_lines = split_string.join(parsed_inputs)
                return insert_lines

            elif symbol_id == "request_params_fields":
                # This converts the ssf_config input list to dictionary fields for the queued request
                # (one-per-line, comma-separated)
                parsed_inputs = []

                # Checks if input format is BaseModel, in which case the params are called from the BaseModel class
                is_basemodel = input_format == "json"

                for param in inputs:
                    # Tell the request dictionary generation handler whether the input format is a BaseModel or not.
                    if param.dtype in handlers["generic"]:
                        parsed_inputs.extend(
                            handler(param.dtype).gen_request_dict(
                                self.ssf_config, param, is_basemodel
                            )
                        )

                    # This should not be called if input format is JSON, but needs to be separately defined anyway
                    # when the input format is Query, `gen_request_dict` does not accept the `is_basemodel` argument.
                    else:
                        parsed_inputs.extend(
                            handler(param.dtype).gen_request_dict(
                                self.ssf_config, param
                            )
                        )

                split_string = ",\n" + " " * indent
                insert_lines = split_string.join(parsed_inputs)
                return insert_lines

            elif symbol_id == "request_meta_fields":
                # This converts the extra metadata to dictionary fields for the queued request (one-per-line, comma-separated)
                meta_fields = []
                meta_fields.extend([f"'endpoint_id' : \"{str(self.endpoint.id)}\""])
                meta_fields.extend(
                    [f"'endpoint_version' : \"{str(self.endpoint.version)}\""]
                )
                meta_fields.extend([f"'endpoint_index' : int({idx})"])

                split_string = ",\n" + " " * indent
                insert_lines = split_string.join(meta_fields)
                return insert_lines

            elif symbol_id == "postprocess":
                # This adds ssf type specific post-processing (multiple lines)
                parsed_inputs = []
                for param in inputs:
                    parsed_inputs.extend(
                        handler(param.dtype).gen_postprocess(self.ssf_config, param)
                    )

                split_string = "\n" + " " * indent
                insert_lines = split_string.join(parsed_inputs)
                return insert_lines

            elif symbol_id == "returns":
                # This adds ssf type specific response (multiple lines)
                parsed_outputs = []
                parsed_fields = []
                parsed_contents = []

                for param in outputs:
                    ret = handler(param.dtype).gen_return(self.ssf_config, param)

                    if type(ret) is tuple:
                        parsed_fields.append(ret)
                    else:
                        parsed_contents.append(ret)

                logger.debug(f"parsed_fields={parsed_fields}")
                logger.debug(f"parsed_contents={parsed_contents}")

                if len(parsed_contents) == 0:
                    # This builds a dictionary of output items from results.
                    # Then makes it ready with jsonable_encoder before
                    # wrapping with a JSONResponse object.
                    # The default headers are also returned.
                    parsed_outputs = ["return_fields = {}"]
                    for f in parsed_fields:
                        param = f[0]
                        astype = f[1]

                        # Generate type mapping for endpoint return fields for defined output type
                        # including support for nested lists.
                        line = gen_output_type_mapping(param, astype)
                        parsed_outputs.extend([f'return_fields["{param}"] = {line}'])

                    parsed_outputs.extend(
                        ["json_compatible_fields = jsonable_encoder(return_fields)"]
                    )
                    parsed_outputs.extend(
                        [
                            "return JSONResponse(content = json_compatible_fields, headers=headers)"
                        ]
                    )

                elif len(parsed_contents) == 1:
                    # Single content returned.
                    # With additional outputs added to the default headers (forced to string type).
                    for f in parsed_fields:
                        param = f[0]
                        astype = "str"
                        parsed_outputs.extend(
                            [f'headers["{param}"] = {astype}(results["{param}"])']
                        )
                    parsed_outputs.extend(
                        [
                            "return Response(",
                            f"    {parsed_contents[0]},",
                            f"    headers=headers",
                            ")",
                        ]
                    )

                else:
                    # Multiple contents returned.
                    # TODO:
                    # Would need to zip (?)
                    raise ValueError(
                        f"Multiple contents not supported {parsed_contents}"
                    )

                split_string = "\n" + " " * indent
                insert_lines = split_string.join(parsed_outputs)
                return insert_lines

            return None

    symbol_parser = FastAPISymbolParser(ssf_config, endpoint)
    # Expand the template.
    expand_template(
        ssf_config,
        template_file,
        application_endpoint,
        [
            symbol_parser,
        ],
    )
