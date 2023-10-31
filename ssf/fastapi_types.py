# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# Handlers SSFTypes for generating FastAPI code

from abc import ABC, abstractmethod
from typing import List, Tuple, Any
from ssf.config import SSFConfig, EndpointParam
from ssf.results import SSFExceptionInternalError, SSFExceptionNotImplementedError

# Create SSFType class for each SSFType we want to support.
# Add the new SSFType (instance) to 'handlers' at the end.
# The existing "Generic" type should work for most I/O since
# it just maps through parameters with no assumption about type.


class SSFType(ABC):
    def __init__(self, typename: str):
        """
        Pre-defines the dtype of the argument based on the map of types from the 'SSF Type' name.

        Parameters:
                typename: The given SSF type name in the SSF Config

        Returns:
                None
        """

    @abstractmethod
    def gen_param(self, ssf_config: SSFConfig, param) -> List[str]:
        """
        Generate FastAPI argument prototype for a parameter of this type.

        Parameters:
                ssf_config (dataclass): The SSF config
                param (dataclass): Metadata describing the param

        Returns:
                Code as a list of lines.
        """
        pass

    @abstractmethod
    def gen_docstring(self, ssf_config: SSFConfig, param) -> List[str]:
        """
        Generate FastAPI docstring for a parameter of this type.

        Parameters:
                ssf_config (dataclass): The SSF config
                param (dataclass): Metadata describing the param

        Returns:
                Code as a list of lines.
        """
        pass

    @abstractmethod
    def gen_preprocess(self, ssf_config: SSFConfig, param) -> List[str]:
        """
        Generate FastAPI code to pre-process a parameter of this type.

        Parameters:
                ssf_config (dataclass): The SSF config
                param (dataclass): Metadata describing the param

        Returns:
                Code as a list of lines.
        """
        pass

    @abstractmethod
    def gen_request_dict(ssf_config: SSFConfig, param) -> List[str]:
        """
        Generate FastAPI code that places a parameter of this type in the request dict.

        Parameters:
                ssf_config (dataclass): The SSF config
                param (dataclass): Metadata describing the param

        Returns:
                Code as a list of lines.
        """
        pass

    @abstractmethod
    def gen_postprocess(ssf_config: SSFConfig, param) -> List[str]:
        """
        Generate FastAPI code to post-process a parameter of this type.

        Parameters:
                ssf_config (dataclass): The SSF config
                param (dataclass): Metadata describing the param

        Returns:
                Code as a list of lines.
        """
        pass

    @abstractmethod
    def gen_return(ssf_config: SSFConfig, param) -> Any:
        """
        Generate FastAPI code that returns a parameter of this type.

        Parameters:
                ssf_config (dataclass): The SSF config
                param (dataclass): Metadata describing the param

        Returns:
                1 - Field as (param,type) tuple which will form JSONResponse or additional header fields if combined with contents.
                or
                2 - Content decl from which to form Response( .... )
        """
        pass

    @abstractmethod
    def gen_example(ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        """
        Generate FastAPI code that provides the example for the type as key:value dictionary entry.

        Parameters:
                ssf_config (dataclass): The SSF config
                param (dataclass): Metadata describing the param

        Returns:
                Code as a list of lines.
        """
        pass


class SSFType_Generic(SSFType):
    def __init__(self, typename: str):
        self.typename = typename

    def get_example_string(self, param: EndpointParam):
        def type_convert(e):
            if "str" in self.typename:
                return f"'{e}'"
            elif "int" in self.typename:
                return f"{int(e)}"
            elif "float" in self.typename:
                return f"{float(e)}"
            elif "bool" in self.typename:
                return f"{e=='True'}"
            return f"'{e}'"

        listof = any(t in self.typename for t in ["List", "list"])
        if listof:
            example = []
            for e in param.example.split(","):
                example.append(type_convert(e))
            example_string = "[" + ",".join(example) + "]"
        else:
            example_string = type_convert(param.example)
        return example_string

    def gen_param(
        self, ssf_config: SSFConfig, param: EndpointParam, is_basemodel: bool = False
    ) -> List[str]:
        if is_basemodel:
            return [f"{param.id}: {self.typename}"]
        # as Query, with example if it exists.
        example = ""
        if param.example is not None:
            example = f"example={self.get_example_string(param)}"
        return [f"{param.id}: {self.typename} = Query({example})"]

    def gen_docstring(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        return [f"- {param.id} : {param.description}"]

    def gen_preprocess(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        return []

    def gen_request_dict(
        self, ssf_config: SSFConfig, param: EndpointParam, is_basemodel: bool = False
    ) -> List[str]:
        return [f"'{param.id}' : {'inputs.' if is_basemodel else ''}{param.id}"]

    def gen_postprocess(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        return []

    def gen_return(self, ssf_config: SSFConfig, param: EndpointParam) -> Any:
        return (f"{param.id}", f"{self.typename}")

    def gen_example(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        param_string = self.get_example_string(param)
        return [f"'{param.id}' : {param_string}"]


class SSFType_PngImageBytes(SSFType):
    """
    - Supports return of a PNG image as bytes (media_type == image/png)
    """

    def __init__(self, typename: str):
        self.typename = typename

    def gen_param(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        raise SSFExceptionNotImplementedError(f"Not implemented {str} {param}")

    def gen_docstring(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        return [f"- {param.id} : {param.description}"]

    def gen_preprocess(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        raise SSFExceptionNotImplementedError(f"Not implemented {str} {param}")

    def gen_request_dict(
        self, ssf_config: SSFConfig, param: EndpointParam
    ) -> List[str]:
        raise SSFExceptionNotImplementedError(f"Not implemented {str} {param}")

    def gen_postprocess(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        raise SSFExceptionNotImplementedError(f"Not implemented {str} {param}")

    def gen_return(
        self, ssf_config: SSFConfig, param: EndpointParam
    ) -> Tuple[List[str], List[str]]:
        param = param.id
        return f'content=results["{param}"], media_type="image/png"'

    def gen_example(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        raise SSFExceptionNotImplementedError(f"Not implemented {str} {param}")


class SSFType_TempFile(SSFType):
    """
    TempFile
    - The TempFile input parameter type is FastAPI's 'UploadFile'.
    - This is pre-processed to a named temporary file.
    - The temporary file filename is queued in the request.
    """

    def __init__(self, typename: str):
        self.typename = typename

    def gen_param(
        self, ssf_config: SSFConfig, param: EndpointParam, is_basemodel: bool = False
    ) -> List[str]:
        return [f"{param.id}: UploadFile = File(...)"]

    def gen_docstring(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        return [f"- {param.id} : {param.description}"]

    def gen_preprocess(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        id = ssf_config.application.id
        param = param.id
        return [
            f"_, extension = os.path.splitext({param}.filename)",
            f'{param}_tmpfile = NamedTemporaryFile(prefix="{id}_", suffix=extension)',
            f"contents = {param}.file.read()",
            f'fp = open({param}_tmpfile.name, "wb")',
            f"fp.write(contents)",
            f"{param}.file.close()",
            f"fp.close()",
        ]

    def gen_request_dict(
        self, ssf_config: SSFConfig, param: EndpointParam
    ) -> List[str]:
        return [f"'{param.id}' : {param.id}_tmpfile.name"]

    def gen_postprocess(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        param = param.id
        return [f"{param}_tmpfile.close()"]

    def gen_return(
        self, ssf_config: SSFConfig, param: EndpointParam
    ) -> Tuple[List[str], List[str]]:
        raise SSFExceptionNotImplementedError(f"Not implemented {str} {param}")

    def gen_example(self, ssf_config: SSFConfig, param: EndpointParam) -> List[str]:
        raise SSFExceptionNotImplementedError(f"Not implemented {str} {param}")


handlers = {
    "generic": {
        "String": "str",
        "Integer": "int",
        "Float": "float",
        "Boolean": "bool",
        "ListAny": "list",
        "ListString": "List[str]",
        "ListInteger": "List[int]",
        "ListFloat": "List[float]",
        "ListBoolean": "List[bool]",
    },
    "custom": {
        "PngImageBytes": SSFType_PngImageBytes("PngImageBytes"),
        "TempFile": SSFType_TempFile("TempFile"),
    },
}

nested_types = {
    "List[str]": ["list", "str"],
    "List[int]": ["list", "int"],
    "List[float]": ["list", "float"],
    "List[bool]": ["list", "bool"],
}


def handler(type: str) -> SSFType:
    if type in handlers["generic"]:
        return SSFType_Generic(handlers["generic"][type])
    elif type in handlers["custom"]:
        return handlers["custom"][type]
    else:
        raise SSFExceptionInternalError(f"No handler to ssf_type {type}")


def gen_output_type_mapping(param: str, astype: str) -> str:
    """
    gen_output_type_mapping

    Parameters:
            param (string): Endpoint input/output name
            astype (string): Mapped Python type for parameter corresponding to `handlers`
    Returns:
            line (string): Line of python code to define the output type for this parameter for the generated endpoint file.

    Operation:
            Generate line of python code to map endpoint output return fields to defined output types, supporting any level of nested depth. First gets parsed order of 'callable' types corresponding to Typing 'definition' type. e.g., `handlers['ListString'] = 'List[str]' -> nested_types['List[str]'] = ['list','str']`. Next defines the depth of the nested type (N), e.g., len(['list','str']) = 2 (list of strings).

            `vars` is an arbitrary loop variable names list for code generation for each level of depth that needs iteration (N-1, which becomes N-2 when the base level is included). Base level is `results[{param}]`, then depth 1 = 'i', depth 2 = 'ii'. e.g., `List[List[str]] -> nt_l = ['list','list','str'], vars = ['result[{param}]', 'i']`

            These are used to generate Python code which maps nested return field to defined nested types as below:

            (*1) Create list openings for all (N-2) levels (multiply operator will repeat string by operand, if 0 it will 'delete' string)

                example d2: List[str] -> ''
                example d3: List[List[str]] -> 'list(['
                example d4: List[List[List[str]]] -> 'list([list(['

            (*2) The most internal part of the list comprehension - a `map` function to check the innermost type (which is necessarily not a list, always int, float, bool, str, etc.,)

                example d2: List[str] -> 'list(map(str, results[{param}]))'
                example d3: List[List[str]] -> 'list(map(str, i))'
                example d4: List[List[List[str]]] -> 'list(map(str, ii))'

            (*3) Join the nested list comprehension to iterate through each depth level in nested list to generate 'for' loop  from the highest depth level to the base level:

                example d2: List[str] -> '' ()
                example d3: List[List[str]] -> 'for i in results[{param}])'
                example d4: List[List[List[str]]] -> 'for ii in i]) for i in results[{param}]])'

            The line is constructed as (*1) + (*2) + (*3) so for each example the constructed Python code is:

                example d2: list(map(str, results[{param}]))
                example d3: list([list(map(str, i)) for i in results[{param}])
                example d4: list([list([list(map(str, ii)) for ii in i]) for i in results[{param}]])
    """
    # TODO: Support dynamic assignment of types in config + allow any List depth level to be defined.

    if astype in nested_types:
        nt_l = nested_types[astype]
        N = len(nt_l)
        vars = [f'results["{param}"]'] + ["i" * (n + 1) for n in range(N - 2)]

        line = (
            f"list([" * (N - 2)  # (*1)
            + f"list(map({nt_l[-1]}, {vars[N-2]})) "  # (*2)
            + " ".join(
                [f"for {vars[rN]} in {vars[rN-1]}])" for rN in range(N - 2, 0, -1)]
            )  # (*3)
        )

    else:
        # Can be explicitly defined if the type is not nested.
        line = f'{astype}(results["{param}"])'

    return line
