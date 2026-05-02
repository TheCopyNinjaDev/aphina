"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-02
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("is_authenticated", sa.Boolean(), nullable=True),
        sa.Column("profile_complete", sa.Boolean(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("target_weight", sa.Float(), nullable=True),
        sa.Column("activity_level", sa.String(length=20), nullable=True),
        sa.Column("daily_calories", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "food_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("food_description", sa.Text(), nullable=True),
        sa.Column("calories", sa.Integer(), nullable=True),
        sa.Column("photo_file_id", sa.String(length=500), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_food_logs_id", "food_logs", ["id"], unique=False)

    op.create_table(
        "milestones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("target_weight", sa.Float(), nullable=True),
        sa.Column("achieved", sa.Boolean(), nullable=True),
        sa.Column("achieved_at", sa.DateTime(), nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_milestones_id", "milestones", ["id"], unique=False)


def downgrade() -> None:
    op.drop_table("milestones")
    op.drop_table("food_logs")
    op.drop_table("users")
