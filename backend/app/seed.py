"""Bootstrap data: ``python -m app.seed [--reference]``.

* Always: the two branches and the first owner account (password from
  ``DOJO_BOOTSTRAP_OWNER_PASSWORD``) when the users table is empty.
* ``--reference``: the academy's programmes, Kajukenbo belt system, membership plans, weekly
  class timetable and inventory catalogue — each only if that table is still empty.

Safe to run repeatedly. Contains no personal data.
"""

import argparse
import asyncio
import sys
from datetime import time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.security import hash_password
from app.curriculum import (
    BELT_EXTRAS,
    BELT_KEYS,
    BRANCH_NAMES_AR,
    PROGRAM_NAMES_AR,
    SKILLS,
)
from app.models import (
    BeltPhase,
    BeltRank,
    BeltSkill,
    Branch,
    ClassSchedule,
    Discipline,
    InventoryItem,
    ItemCategory,
    MembershipPlan,
    Program,
    Role,
    Track,
    User,
)

BRANCHES = [
    {"name": "Promenade", "code": "PRM", "address": "Hawalli"},
    {"name": "Bedaya", "code": "BDY", "address": "Sabah Al Salem"},
]

PROGRAMS = [
    ("Kids Kajukenbo", Discipline.KAJUKENBO, 5, 12),
    ("Adult Kajukenbo", Discipline.KAJUKENBO, 13, None),
    ("Kickboxing (All Levels)", Discipline.KICKBOXING, None, None),
    ("Jiujitsu (All Levels)", Discipline.JIUJITSU, None, None),
    ("Open Mat / Sparring", Discipline.OPEN_MAT, None, None),
    ("Self-Defence & Traditional Seminar", Discipline.SELF_DEFENCE, None, None),
]

# One belt, one stripe, three arts: the belt is the Kajukenbo rank and kickboxing level; the
# stripe is the grappling (BJJ-equivalent) level; seminar points are needed for promotion.
BELTS = [
    ("White", "#f5f5f5", BeltPhase.BEGINNER, None, None, 0),
    ("Yellow", "#facc15", BeltPhase.BEGINNER, "1 white stripe", "BJJ White (in progress)", 2),
    ("Purple", "#7e22ce", BeltPhase.BEGINNER, "2 white stripes", "BJJ White (completing)", 4),
    ("Blue", "#2563eb", BeltPhase.INTERMEDIATE, "Belt is the marker", "BJJ Blue (earned)", 6),
    ("Green", "#16a34a", BeltPhase.INTERMEDIATE, "1 blue stripe", "BJJ Blue (progressing)", 8),
    ("Brown", "#78350f", BeltPhase.ADVANCED, "1 blue stripe", "BJJ Blue (completing)", 10),
    ("Brown / Black Stripe", "#3f1d0b", BeltPhase.ADVANCED, "1 purple stripe", "BJJ Purple", 11),
    ("Black", "#111111", BeltPhase.EXPERT, "1 purple stripe", "BJJ Purple (confirmed)", 12),
]

# (name, branch code or None for academy-wide, days, price in KD)
PLANS = [
    ("Promenade Monthly (striking + grappling)", "PRM", 30, "85.000"),
    ("Bedaya Kids Monthly", "BDY", 30, "65.000"),
    ("Bedaya Adults Monthly", "BDY", 30, "55.000"),
    ("Trial Class", None, 1, "0.000"),
]

# Weekly timetable: four 40-minute blocks, alternating grappling and striking.
SLOTS = [(time(16, 30), time(17, 10)), (time(17, 15), time(17, 55)),
         (time(18, 0), time(18, 40)), (time(18, 45), time(19, 25))]  # fmt: skip
TRAINING_DAYS = [6, 7, 1, 2, 3, 4]  # ISO weekdays Saturday .. Thursday


def _catalogue() -> list[tuple[str, str, ItemCategory, str | None, str, int]]:
    """(sku, name, category, size, price in KD, reorder level)"""
    uniform, belt, gear = ItemCategory.UNIFORM, ItemCategory.BELT, ItemCategory.PROTECTIVE_GEAR
    items = [(f"GI-K-{s}", "Kids Gi", uniform, str(s), "15.000", 3) for s in range(110, 160, 10)]
    items += [(f"GI-A-{s}", "Adult Gi", uniform, s, "22.000", 2) for s in ("A1", "A2", "A3")]
    items += [
        (f"BELT-{i:02d}", f"{b[0]} Belt", belt, None, "3.000", 5) for i, b in enumerate(BELTS, 1)
    ]
    items += [(f"GLV-{s}", "Boxing Gloves", gear, f"{s}oz", "12.500", 2) for s in (8, 10, 12, 14)]
    items += [(f"SHIN-{s}", "Shin Guards", gear, s, "10.000", 2) for s in ("S", "M", "L")]
    items += [
        ("MOUTH-STD", "Mouth Guard", gear, None, "2.500", 5),
        ("RASH-M", "Rash Guard", ItemCategory.MERCHANDISE, "M", "9.000", 2),
    ]
    return items


async def _empty(db: AsyncSession, model) -> bool:
    return not await db.scalar(select(func.count()).select_from(model))


async def seed_reference(db: AsyncSession) -> None:
    branches = {b.code: b for b in await db.scalars(select(Branch))}
    if await _empty(db, Program):
        db.add_all(
            Program(name=n, name_ar=PROGRAM_NAMES_AR.get(n), discipline=d, min_age=lo, max_age=hi)
            for n, d, lo, hi in PROGRAMS
        )
    if await _empty(db, BeltRank):
        db.add_all(
            BeltRank(
                name=n,
                color=c,
                sort_order=i,
                phase=p,
                bjj_stripe=stripe,
                bjj_equivalent=bjj,
                seminars_required=sem,
                name_ar=BELT_EXTRAS[key][0],
                bjj_stripe_ar=BELT_EXTRAS[key][2],
                min_classes=BELT_EXTRAS[key][3],
                min_weeks=BELT_EXTRAS[key][4],
                min_evaluations=BELT_EXTRAS[key][5],
            )
            for i, ((n, c, p, stripe, bjj, sem), key) in enumerate(
                zip(BELTS, BELT_KEYS, strict=True), start=1
            )
        )
        await db.flush()
    if await _empty(db, BeltSkill):
        belts = list(await db.scalars(select(BeltRank).order_by(BeltRank.sort_order)))
        if len(belts) == len(BELT_KEYS):
            db.add_all(
                BeltSkill(belt_rank_id=belt.id, track=track, category=cat, name=name, sort_order=i)
                for belt, key in zip(belts, BELT_KEYS, strict=True)
                for track in Track
                for i, (cat, name) in enumerate(SKILLS.get(f"{track.value}:{key}", []))
            )
    if await _empty(db, MembershipPlan):
        db.add_all(
            MembershipPlan(
                name=n,
                branch_id=branches[code].id if code else None,
                duration_days=days,
                price=Decimal(price),
            )
            for n, code, days, price in PLANS
            if code is None or code in branches
        )
    await db.flush()
    if await _empty(db, ClassSchedule):
        programs = {p.discipline: p.id for p in await db.scalars(select(Program))}
        for branch in branches.values():
            for weekday in TRAINING_DAYS:
                for i, (start, end) in enumerate(SLOTS):
                    grappling_first = weekday in (6, 1, 3)  # Sat, Mon, Wed open with grappling
                    grappling = (i % 2 == 0) == grappling_first
                    discipline = Discipline.JIUJITSU if grappling else Discipline.KICKBOXING
                    db.add(
                        ClassSchedule(
                            branch_id=branch.id,
                            program_id=programs[discipline],
                            weekday=weekday,
                            start_time=start,
                            end_time=end,
                            capacity=20,
                        )
                    )
    if await _empty(db, InventoryItem):
        db.add_all(
            InventoryItem(
                sku=sku, name=n, category=cat, size=size, unit_price=Decimal(p), reorder_level=r
            )
            for sku, n, cat, size, p, r in _catalogue()
        )


async def seed(reference: bool) -> None:
    s = get_settings()
    async with get_sessionmaker()() as db:
        if await _empty(db, Branch):
            db.add_all(Branch(**b, name_ar=BRANCH_NAMES_AR.get(b["name"])) for b in BRANCHES)
            await db.flush()

        if await _empty(db, User):
            pw = s.bootstrap_owner_password.get_secret_value() if s.bootstrap_owner_password else ""
            if len(pw) < 10:
                sys.exit("Set DOJO_BOOTSTRAP_OWNER_PASSWORD (10+ characters) to create the owner.")
            db.add(
                User(
                    username=s.bootstrap_owner_username,
                    full_name="Academy Owner",
                    role=Role.OWNER,
                    password_hash=await hash_password(pw),
                )
            )
        if reference:
            await seed_reference(db)
        await db.commit()
    await dispose_engine()
    print("Seed complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", action="store_true", help="load academy reference data")
    asyncio.run(seed(parser.parse_args().reference))
