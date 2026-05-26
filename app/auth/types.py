from typing import Literal
from pydantic import BaseModel


class BearerTokenEntry(BaseModel):
    id: str
    token: str
    type: Literal["user", "service"] = "service"