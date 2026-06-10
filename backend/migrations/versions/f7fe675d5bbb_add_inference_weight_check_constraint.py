"""add_inference_weight_check_constraint

Revision ID: f7fe675d5bbb
Revises: fe655a941719
Create Date: 2026-06-10 11:24:20.872259

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7fe675d5bbb"
down_revision: str | Sequence[str] | None = "fe655a941719"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "check_inference_weight_values",
        "scheme_nodes",
        "scheme != 'INFERENCE' OR weight IN (1.0, 2.0, 5.0)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("check_inference_weight_values", "scheme_nodes", type_="check")
