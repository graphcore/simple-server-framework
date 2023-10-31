# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
from ssf.application import SSFApplicationInterface
from ssf.results import *


logger = logging.getLogger()


class MyApplication(SSFApplicationInterface):
    def verify_config(self, label: str):
        def lookup_dict(d, ref):
            fields = ref.split(".")
            for f in fields:
                try:
                    t = type(d[f]).__name__
                    d = d[f]
                except:
                    return None, None
            if isinstance(d, set):
                d = sorted(d)
            return d, t

        def lookup_config(ref):
            if self.ssf_config.config_dict is None:
                return None, None
            return lookup_dict(self.ssf_config.config_dict, ref)

        def lookup_context(ref):
            if self.context is None:
                return None, None
            return lookup_dict(self.context, ref)

        def lookup_args(ref):
            if self.ssf_config.args is None:
                return None, None
            return lookup_dict(vars(self.ssf_config.args), ref)

        logger.info(f"> Verify {label} context.status=={lookup_context('status')}")
        logger.info(
            f"> Verify {label} args.modify_config=={lookup_args('modify_config')}"
        )
        logger.info(
            f"> Verify {label} application.trace=={lookup_config('application.trace')}"
        )
        logger.info(
            f"> Verify {label} application.custom=={lookup_config('application.custom')}"
        )
        logger.info(f"> Verify {label} testlist=={lookup_config('testlist')}")
        logger.info(f"> Verify {label} testlist_dict=={lookup_config('testlist_dict')}")
        logger.info(f"> Verify {label} newlist=={lookup_config('newlist')}")
        logger.info(f"> Verify {label} testtypes=={lookup_config('testtypes')}")

    def __init__(self, ssf_config):
        assert ssf_config is not None
        assert ssf_config.config_dict is not None
        self.ssf_config = ssf_config
        self.context = ssf_config.config_dict
        if "status" in self.context:
            self.context["status"].add("__init__")
        else:
            self.context["status"] = {"__init__"}
        self.verify_config("__init__")

    def build(self) -> int:
        logger.info("MyApp build")
        self.context["status"].add("build")
        self.verify_config("build")
        return RESULT_OK

    def startup(self) -> int:
        logger.info("MyApp startup")
        self.context["status"].add("startup")
        self.verify_config("startup")
        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        self.context["status"].add("request")
        self.verify_config("request")
        return {"response": "ok"}

    def shutdown(self) -> int:
        logger.info("MyApp shutdown")
        self.context["status"].add("shutdown")
        self.verify_config("shutdown")
        return RESULT_OK

    def watchdog(self) -> int:
        logger.info("MyApp watchdog")
        self.context["status"].add("watchdog")
        self.verify_config("watchdog")
        return RESULT_OK
