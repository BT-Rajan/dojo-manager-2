from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class InModel(BaseModel):
    """Request bodies: reject unknown fields and trim strings."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


Name = Annotated[str, StringConstraints(min_length=1, max_length=150)]
ShortText = Annotated[str, StringConstraints(max_length=255)]
LongText = Annotated[str, StringConstraints(max_length=5000)]
Phone = Annotated[str, StringConstraints(min_length=3, max_length=30, pattern=r"^[0-9+()\-\s]+$")]
# Kuwaiti dinar has 3 decimal places (fils).
Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)]
