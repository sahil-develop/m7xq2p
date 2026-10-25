"""Create wind actual, forecast, and import state tables.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wind_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publish_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation_mw", sa.Float(), nullable=False),
        sa.UniqueConstraint("start_time", "publish_time", name="uq_forecast_start_publish"),
    )
    op.create_index("ix_forecast_start_publish", "wind_forecasts", ["start_time", "publish_time"])
    op.create_table(
        "wind_actuals",
        sa.Column("start_time", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("generation_mw", sa.Float(), nullable=False),
    )
    op.create_index("ix_actual_start_time", "wind_actuals", ["start_time"])
    op.create_table(
        "import_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("import_state")
    op.drop_index("ix_actual_start_time", table_name="wind_actuals")
    op.drop_table("wind_actuals")
    op.drop_index("ix_forecast_start_publish", table_name="wind_forecasts")
    op.drop_table("wind_forecasts")
