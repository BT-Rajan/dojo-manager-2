from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    field_serializer,
)

from app.core.clock import to_local, to_utc_naive


class InModel(BaseModel):
    """Request bodies: reject unknown fields and trim strings."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", mode="wrap", when_used="json")
    def _academy_time(self, value: Any, handler: SerializerFunctionWrapHandler) -> Any:
        # Stored timestamps are UTC; clients receive academy (Kuwait) time with its offset,
        # e.g. 2026-10-20T16:56:00+03:00.
        if isinstance(value, datetime):
            return to_local(value).isoformat(timespec="seconds")
        return handler(value)


Name = Annotated[str, StringConstraints(min_length=1, max_length=150)]
ShortText = Annotated[str, StringConstraints(max_length=255)]
LongText = Annotated[str, StringConstraints(max_length=5000)]
Phone = Annotated[str, StringConstraints(min_length=3, max_length=30, pattern=r"^[0-9+()\-\s]+$")]
# Kuwaiti dinar has 3 decimal places (fils).
Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)]

# Incoming timestamp: naive values are academy local time; stored as naive UTC.
LocalDateTime = Annotated[datetime, AfterValidator(to_utc_naive)]
