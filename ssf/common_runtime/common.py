# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from pydantic import BaseModel

# Model describing schema for APIs that can throw HTTPExceptions.
class HTTPError(BaseModel):
    detail: str

    class Config:
        schema_extra = {
            "example": {"detail": "Reason for the HTTPException"},
        }
