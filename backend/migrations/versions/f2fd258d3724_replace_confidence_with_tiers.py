"""replace_confidence_with_tiers

Revision ID: f2fd258d3724
Revises: 35153f64597a
Create Date: 2026-06-09 16:50:33.621892

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2fd258d3724"
down_revision: str | Sequence[str] | None = "35153f64597a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create enums
    sa_tier_kind = sa.Enum(
        "certain", "fort", "moyen", "faible", "speculatif", name="tierkind"
    )
    sa_weight_kind = sa.Enum("credence", "engagement", name="weightkind")

    sa_tier_kind.create(op.get_bind(), checkfirst=True)
    sa_weight_kind.create(op.get_bind(), checkfirst=True)

    # 2. Add columns
    op.add_column("nodes", sa.Column("tier", sa_tier_kind, nullable=True))
    op.add_column("nodes", sa.Column("weight_kind", sa_weight_kind, nullable=True))
    op.add_column(
        "nodes", sa.Column("weight", sa.Float(), nullable=False, server_default="0.6")
    )

    # 3. Backfill data
    connection = op.get_bind()
    metadata = sa.MetaData()
    nodes_table = sa.Table(
        "nodes",
        metadata,
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("type", sa.String()),
        sa.Column("confidence", sa.Float()),
        sa.Column("tier", sa_tier_kind),
        sa.Column("weight_kind", sa_weight_kind),
        sa.Column("weight", sa.Float()),
    )

    select_query = sa.select(
        nodes_table.c.id, nodes_table.c.type, nodes_table.c.confidence
    )
    results = connection.execute(select_query).fetchall()

    for row in results:
        node_id = row[0]
        node_type = row[1]
        conf = row[2]

        # Determine tier
        if conf > 0.875:
            tier = "certain"
            weight = 0.95
        elif conf > 0.700:
            tier = "fort"
            weight = 0.80
        elif conf > 0.500:
            tier = "moyen"
            weight = 0.60
        elif conf > 0.300:
            tier = "faible"
            weight = 0.40
        else:
            tier = "speculatif"
            weight = 0.20

        # Determine weight_kind
        if node_type in ("descriptif", "empirique", "definitionnel"):
            w_kind = "credence"
        else:
            w_kind = "engagement"

        # Update row
        update_query = (
            sa.update(nodes_table)
            .where(nodes_table.c.id == node_id)
            .values(tier=tier, weight_kind=w_kind, weight=weight)
        )
        connection.execute(update_query)

    # 4. Remove confidence and its check constraint
    op.execute("ALTER TABLE nodes DROP CONSTRAINT IF EXISTS check_confidence_range")
    op.drop_column("nodes", "confidence")


def downgrade() -> None:
    """Downgrade schema."""
    # Add confidence column back
    op.add_column("nodes", sa.Column("confidence", sa.Float(), nullable=True))

    # Backfill confidence from weight
    connection = op.get_bind()
    metadata = sa.MetaData()
    nodes_table = sa.Table(
        "nodes",
        metadata,
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("weight", sa.Float()),
        sa.Column("confidence", sa.Float()),
    )

    select_query = sa.select(nodes_table.c.id, nodes_table.c.weight)
    results = connection.execute(select_query).fetchall()

    for row in results:
        node_id = row[0]
        weight = row[1]

        update_query = (
            sa.update(nodes_table)
            .where(nodes_table.c.id == node_id)
            .values(confidence=weight)
        )
        connection.execute(update_query)

    op.alter_column("nodes", "confidence", nullable=False)

    # Re-add constraint
    op.create_check_constraint(
        "check_confidence_range", "nodes", "confidence >= 0.0 AND confidence <= 1.0"
    )

    # Drop new columns
    op.drop_column("nodes", "tier")
    sa_tier_kind = sa.Enum(
        "certain", "fort", "moyen", "faible", "speculatif", name="tierkind"
    )
    sa_tier_kind.drop(op.get_bind(), checkfirst=True)

    op.drop_column("nodes", "weight_kind")
    sa_weight_kind = sa.Enum("credence", "engagement", name="weightkind")
    sa_weight_kind.drop(op.get_bind(), checkfirst=True)

    op.drop_column("nodes", "weight")
