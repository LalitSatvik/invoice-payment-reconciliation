"""add candidate_claimed_elsewhere exception reason

Revision ID: 6bc391235a79
Revises: ccea83082431
Create Date: 2026-08-26 02:04:14.241886

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6bc391235a79'
down_revision: Union[str, None] = 'ccea83082431'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The matching engine (Task 5) emits a fourth exception reason beyond the
# three the schema originally had a slot for: a record with exactly one
# uncontested, above-threshold candidate that nonetheless lost the
# mutual-best pairing to a rival claim on the other side. This migration
# only adds that value to the existing ``exception_reason`` enum; it must
# never be combined, in the same revision, with anything that *uses* the
# new value (e.g. a data migration inserting a row with this reason) --
# Postgres does not allow a newly added enum value to be referenced in the
# same transaction that added it.
NEW_VALUE = "candidate_claimed_elsewhere"

# The full old value set, needed to rebuild the type on downgrade since
# Postgres has no ``ALTER TYPE ... DROP VALUE``.
OLD_VALUES = (
    "no_candidate",
    "ambiguous_multiple_candidates",
    "below_threshold",
    "possible_split_payment",
    "rejected_by_reviewer",
    "amount_mismatch_only",
)


def upgrade() -> None:
    op.execute(f"ALTER TYPE exception_reason ADD VALUE IF NOT EXISTS '{NEW_VALUE}'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value in place, so the type is
    # rebuilt from the old value set. This will fail if any ``exception``
    # row currently uses the new value -- that data loss must be resolved
    # by hand (reassign or delete those rows) before downgrading, rather
    # than silently discarded here.
    op.execute("ALTER TYPE exception_reason RENAME TO exception_reason_old")

    old_enum = postgresql.ENUM(*OLD_VALUES, name="exception_reason")
    old_enum.create(op.get_bind())

    op.execute(
        "ALTER TABLE exception "
        "ALTER COLUMN reason TYPE exception_reason "
        "USING reason::text::exception_reason"
    )

    op.execute("DROP TYPE exception_reason_old")
