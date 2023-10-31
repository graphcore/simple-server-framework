# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.responses import RedirectResponse
from fastapi.security.api_key import APIKey, APIKeyCookie, APIKeyHeader, APIKeyQuery

from starlette.status import HTTP_403_FORBIDDEN

from secrets import compare_digest

from ssf.common_runtime.config import settings

API_KEY_NAME = "api_key"

api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_key_cookie = APIKeyCookie(name=API_KEY_NAME, auto_error=False)


async def get_api_key(
    api_key_query: str = Security(api_key_query),
    api_key_header: str = Security(api_key_header),
    api_key_cookie: str = Security(api_key_cookie),
):
    if settings.api_key is None:
        # No API key specified!
        return True
    elif api_key_query and compare_digest(api_key_query, settings.api_key):
        return api_key_query
    elif api_key_header and compare_digest(api_key_header, settings.api_key):
        return api_key_header
    elif api_key_cookie and compare_digest(api_key_cookie, settings.api_key):
        return api_key_cookie
    else:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"Invalid credentials (Login first with /login?{API_KEY_NAME}=<key>)",
        )


router = APIRouter(tags=["Security"])


@router.get("/login")
async def security_login(api_key: APIKey = Depends(get_api_key)):
    response = RedirectResponse(url="/")
    response.set_cookie(
        API_KEY_NAME,
        value=api_key,
        # TODO: this cookie should probably be better httponly
        # changed temporarily to allow cookie to be read by frontend
        # httponly=True,
        max_age=settings.api_key_timeout,
    )
    return response


@router.get("/logout")
async def security_logout():
    response = RedirectResponse(url="/")
    response.delete_cookie(API_KEY_NAME)
    return response
