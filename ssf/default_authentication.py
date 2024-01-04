# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from secrets import compare_digest

# This module provides a default implementation of a session
# authentication function that can be used to authenticate a given
# username and password when --enable-session-authentication has
# been enabled and the /session_login entry point is called.
# Use the --session-authentication-module-file argument to specify
# this file or to specify your own custom implementation file.


def db_lookup_user(username: str):
    users = {
        "test": {
            "password": "123456",
            "uid": 1,
        },
    }
    return users.get(username)


def authenticate_user(username: str, password: str):
    """
    Authenticate a username and password.
    This is a reference/test implementation.

    The returned user id string will be logged for information by SSF.
    SSF will concatentate the returned user id string with a generated
    token to form a session key that is returned as a cookie and will
    permit subsequent endpoint access.

    The same user_id is passed through to the application request()
    function in the meta dictionary with key "user_id".

    Returns:
            None to refuse access.
            A unique "user id" as a string to permit access.
    """
    user_account = db_lookup_user(username)
    if user_account and compare_digest(password, user_account["password"]):
        return str(user_account["uid"])
    return None
