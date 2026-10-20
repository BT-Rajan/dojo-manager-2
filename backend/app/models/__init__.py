"""Import every model module so ``Base.metadata`` is complete (used by Alembic and tests)."""

from app.models.base import Base
from app.models.dojo import (
    BeltPhase,
    BeltRank,
    Discipline,
    Gender,
    Instructor,
    Member,
    Membership,
    MembershipPlan,
    MembershipStatus,
    MemberStatus,
    Payment,
    PaymentCategory,
    PaymentMethod,
    Program,
)
from app.models.org import AuditLog, Branch, Role, User, UserSession, user_branches

__all__ = [
    "AuditLog",
    "Base",
    "BeltPhase",
    "BeltRank",
    "Branch",
    "Discipline",
    "Gender",
    "Instructor",
    "Member",
    "MemberStatus",
    "Membership",
    "MembershipPlan",
    "MembershipStatus",
    "Payment",
    "PaymentCategory",
    "PaymentMethod",
    "Program",
    "Role",
    "User",
    "UserSession",
    "user_branches",
]
