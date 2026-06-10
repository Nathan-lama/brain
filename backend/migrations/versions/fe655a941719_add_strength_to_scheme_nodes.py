"""add_strength_to_scheme_nodes

Revision ID: fe655a941719
Revises: f2fd258d3724
Create Date: 2026-06-09 22:16:37.616758

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe655a941719"
down_revision: str | Sequence[str] | None = "f2fd258d3724"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Drop old constraint
    op.execute("ALTER TABLE scheme_nodes DROP CONSTRAINT IF EXISTS check_weight_range")

    # 2. Create PG Enum
    sa_scheme_strength = sa.Enum(
        "deductif", "defaisable_fort", "defaisable_faible", name="schemestrength"
    )
    sa_scheme_strength.create(op.get_bind(), checkfirst=True)

    # 3. Add column strength
    op.add_column(
        "scheme_nodes", sa.Column("strength", sa_scheme_strength, nullable=True)
    )

    # 4. Backfill existing inferences
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE scheme_nodes SET weight = 1.0, strength = 'defaisable_faible'::schemestrength WHERE scheme = 'INFERENCE'::schemetype"
        )
    )

    # 5. Re-add constraint allowing up to 5.0
    op.create_check_constraint(
        "check_weight_range", "scheme_nodes", "weight >= 0.0 AND weight <= 5.0"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Drop check constraint
    op.execute("ALTER TABLE scheme_nodes DROP CONSTRAINT IF EXISTS check_weight_range")

    # 2. Reset weights > 1.0 to 1.0
    connection = op.get_bind()
    metadata = sa.MetaData()
    scheme_nodes_table = sa.Table(
        "scheme_nodes",
        metadata,
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("weight", sa.Float()),
    )
    update_query = (
        sa.update(scheme_nodes_table)
        .where(scheme_nodes_table.c.weight > 1.0)
        .values(weight=1.0)
    )
    connection.execute(update_query)

    # 3. Drop column strength
    op.drop_column("scheme_nodes", "strength")

    # 4. Drop PG Enum
    sa_scheme_strength = sa.Enum(
        "deductif", "defaisable_fort", "defaisable_faible", name="schemestrength"
    )
    sa_scheme_strength.drop(op.get_bind(), checkfirst=True)

    # 5. Re-add old check constraint
    op.create_check_constraint(
        "check_weight_range", "scheme_nodes", "weight >= 0.0 AND weight <= 1.0"
    )
