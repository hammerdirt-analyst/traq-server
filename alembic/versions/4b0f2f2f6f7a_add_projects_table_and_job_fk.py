"""add projects table and job project foreign key

Revision ID: 4b0f2f2f6f7a
Revises: d5a83498da59
Create Date: 2026-03-28 18:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4b0f2f2f6f7a"
down_revision: Union[str, None] = "d5a83498da59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_project_id"), "projects", ["project_id"], unique=True)
    op.create_index(op.f("ix_projects_name"), "projects", ["name"], unique=True)
    op.create_index(op.f("ix_projects_slug"), "projects", ["slug"], unique=True)

    op.add_column("jobs", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_jobs_project_id"), "jobs", ["project_id"], unique=False)
    op.create_foreign_key(
        "fk_jobs_project_id_projects",
        "jobs",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_project_id_projects", "jobs", type_="foreignkey")
    op.drop_index(op.f("ix_jobs_project_id"), table_name="jobs")
    op.drop_column("jobs", "project_id")

    op.drop_index(op.f("ix_projects_slug"), table_name="projects")
    op.drop_index(op.f("ix_projects_name"), table_name="projects")
    op.drop_index(op.f("ix_projects_project_id"), table_name="projects")
    op.drop_table("projects")
