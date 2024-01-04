# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.responses import RedirectResponse
from fastapi.security.api_key import APIKey, APIKeyCookie
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from secrets import token_hex
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from ssf.application_interface.runtime_settings import settings
from ssf.application_interface.utils import load_module
from ssf.application_interface.results import SSFExceptionApplicationModuleError

import inspect
import logging

logger = logging.getLogger()

SESSION_KEY_NAME = "session_key"
SESSION_KEY_TOKEN_PREFIX_CHARS = 16

USER_AUTHENTICATION_MODULE_NAME = "authenticate_user"
USER_AUTHENTICATION_FUNCTION_NAME = "authenticate_user"

session_key_cookie = APIKeyCookie(name=SESSION_KEY_NAME, auto_error=False)

router = APIRouter(tags=["Security"])

security = HTTPBasic()

# Map of session keys back to user ids
sessions = {}


def get_user_authenticator():
    USER_AUTHENTICATION_MODULE_FILE = settings.session_authentication_module_file
    authentication_module = load_module(
        USER_AUTHENTICATION_MODULE_FILE, USER_AUTHENTICATION_MODULE_NAME
    )
    for _, obj in inspect.getmembers(authentication_module):
        if (
            inspect.isfunction(obj)
            and obj.__name__ == USER_AUTHENTICATION_FUNCTION_NAME
        ):
            return obj
    raise SSFExceptionApplicationModuleError(
        f"Failure finding {USER_AUTHENTICATION_FUNCTION_NAME} in {USER_AUTHENTICATION_MODULE_FILE}."
    )


async def get_session_key(
    session_key_cookie: str = Security(session_key_cookie),
):
    if not settings.enable_session_authentication:
        # Authentication is not enabled!
        return None
    elif session_key_cookie:
        if session_key_cookie in sessions:
            return session_key_cookie
    else:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"Invalid session (Login first with /session_login)",
        )


async def check_session_key(
    session_key_cookie: str = Security(session_key_cookie),
):
    if session_key_cookie and session_key_cookie in sessions:
        return session_key_cookie
    return None


async def authenticate_user(
    credentials: HTTPBasicCredentials = Depends(security),
    session_key: APIKey = Depends(check_session_key),
):
    if session_key is not None:
        delete_session(session_key)
    authenticator = get_user_authenticator()
    if authenticator:
        user_id = authenticator(credentials.username, credentials.password)
        if user_id:
            logger.info(f"Authorized {credentials.username} as user_id {user_id}")
            return str(user_id)
    else:
        logger.error(f"Missing authenticator")
    logger.error(f"Failed to authenticate user {credentials.username}")
    raise HTTPException(
        status_code=HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


def create_session_for_user(user_id: str):
    # The session cookie is returned as a token prefix of known fixed
    # length (SESSION_KEY_TOKEN_PREFIX_CHARS) with user id appended.
    # token_hex(N) returns a token of size N bytes, returned as hex-char pairs,
    # so SESSION_KEY_TOKEN_PREFIX_CHARS **must** be even length.
    assert SESSION_KEY_TOKEN_PREFIX_CHARS % 2 == 0
    session_key = token_hex(int(SESSION_KEY_TOKEN_PREFIX_CHARS / 2)) + user_id
    sessions[session_key] = user_id
    logger.info(f"> Created session for user_id {user_id} session_key {session_key}")
    return session_key


def delete_session(session_key):
    user_id = get_user_id_from_session(session_key)
    sessions.pop(session_key)
    logger.info(f"> Deleted session for user_id {user_id} session_key {session_key}")


def get_user_id_from_session(session_key: str):
    if session_key is None or session_key not in sessions:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid session ID",
        )
    user = sessions[session_key]
    return user


@router.get("/session_login")
async def session_login(user_id: str = Depends(authenticate_user)):
    session_key = create_session_for_user(user_id)
    response = RedirectResponse(url="/")
    response.set_cookie(
        SESSION_KEY_NAME,
        value=session_key,
        max_age=settings.session_authentication_timeout,
    )
    return response


@router.get("/session_logout")
async def session_logout(session_key: APIKey = Depends(get_session_key)):
    delete_session(session_key)
    response = RedirectResponse(url="/")
    response.delete_cookie(SESSION_KEY_NAME)
    return response


@router.get("/session_status")
async def get_current_user(session_key: APIKey = Depends(get_session_key)):
    message = {"user_id": get_user_id_from_session(session_key)}
    return message
