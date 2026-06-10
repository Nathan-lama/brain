"""add_inference_strength_not_null_check_constraint

Revision ID: c1abeaf5d2a2
Revises: f7fe675d5bbb
Create Date: 2026-06-10 11:26:03.656998

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1abeaf5d2a2"
down_revision: str | Sequence[str] | None = "f7fe675d5bbb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "check_inference_strength_not_null",
        "scheme_nodes",
        "scheme != 'INFERENCE' OR strength IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "check_inference_strength_not_null", "scheme_nodes", type_="check"
    )
