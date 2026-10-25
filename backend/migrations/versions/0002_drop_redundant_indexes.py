"""Drop indexes duplicated by the unique constraint and the primary key.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # uq_forecast_start_publish and the wind_actuals primary key already index these columns.
    op.drop_index("ix_forecast_start_publish", table_name="wind_forecasts")
    op.drop_index("ix_actual_start_time", table_name="wind_actuals")
    op.add_column(
        "import_state",
        sa.Column("forecast_rows", sa.Integer(), nullable=True),
    )
    op.add_column(
        "import_state",
        sa.Column("actual_rows", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("import_state", "actual_rows")
    op.drop_column("import_state", "forecast_rows")
    op.create_index("ix_actual_start_time", "wind_actuals", ["start_time"])
    op.create_index("ix_forecast_start_publish", "wind_forecasts", ["start_time", "publish_time"])
