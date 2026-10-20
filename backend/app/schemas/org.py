from datetime import datetime
from typing import Annotated

from pydantic import EmailStr, Field, StringConstraints

from app.models.org import Role
from app.schemas.common import InModel, Name, OutModel, Phone, ShortText

Username = Annotated[
    str, StringConstraints(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$")
]
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]


class LoginIn(InModel):
    username: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class BranchIn(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    code: Annotated[str, StringConstraints(min_length=1, max_length=20, pattern=r"^[A-Z0-9_\-]+$")]
    address: ShortText | None = None
    phone: Phone | None = None
    is_active: bool = True


class BranchUpdate(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    address: ShortText | None = None
    phone: Phone | None = None
    is_active: bool | None = None


class BranchOut(OutModel):
    id: int
    name: str
    code: str
    address: str | None
    phone: str | None
    is_active: bool


class UserCreate(InModel):
    username: Username
    full_name: Name
    email: EmailStr | None = None
    password: Password
    role: Role = Role.BRANCH_ADMIN
    branch_ids: list[int] = Field(default_factory=list, max_length=50)


class UserUpdate(InModel):
    full_name: Name | None = None
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None
    branch_ids: list[int] | None = Field(default=None, max_length=50)


class PasswordReset(InModel):
    password: Password


class PasswordChange(InModel):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password


class UserOut(OutModel):
    id: int
    username: str
    full_name: str
    email: str | None
    role: Role
    is_active: bool
    last_login_at: datetime | None
    branches: list[BranchOut]
