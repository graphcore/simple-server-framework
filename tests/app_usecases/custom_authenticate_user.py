# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from secrets import compare_digest


def authenticate_user(username: str, password: str):
    if compare_digest(username, "freddy") and compare_digest(password, "password"):
        return "freddy"
    return None
