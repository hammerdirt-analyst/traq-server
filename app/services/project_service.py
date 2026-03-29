"""Project registry service for optional job-level grouping metadata."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from ..db import session_scope
from ..db_models import Project


_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ProjectService:
    """Create, update, list, and resolve server-managed projects."""

    @staticmethod
    def _clean(value: str | None) -> str | None:
        """Trim optional free-form input and normalize blanks to ``None``."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _slugify(value: str) -> str:
        """Generate a normalized slug for one project label."""
        normalized = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
        return normalized or "project"

    @staticmethod
    def _to_dict(row: Project) -> dict[str, Any]:
        """Serialize one project row for API and CLI callers."""
        return {
            "project_id": row.project_id,
            "project": row.name,
            "project_slug": row.slug,
        }

    def list_projects(self) -> list[dict[str, Any]]:
        """Return all server-managed projects ordered by name."""
        with session_scope() as session:
            rows = session.scalars(select(Project).order_by(Project.name)).all()
            return [self._to_dict(row) for row in rows]

    def create_project(self, *, project: str, project_slug: str | None = None) -> dict[str, Any]:
        """Create one project with a stable server-owned identifier."""
        name = self._clean(project)
        if not name:
            raise ValueError("Project name is required")
        slug = self._clean(project_slug) or self._slugify(name)
        with session_scope() as session:
            existing_name = session.scalar(select(Project).where(Project.name == name))
            if existing_name is not None:
                raise ValueError(f"Project already exists: {name}")
            existing_slug = session.scalar(select(Project).where(Project.slug == slug))
            if existing_slug is not None:
                raise ValueError(f"Project slug already exists: {slug}")
            row = Project(
                project_id=f"project_{uuid4().hex[:12]}",
                name=name,
                slug=slug,
            )
            session.add(row)
            session.flush()
            return self._to_dict(row)

    def update_project(
        self,
        project_ref: str,
        *,
        project: str | None = None,
        project_slug: str | None = None,
    ) -> dict[str, Any]:
        """Update one project label and/or slug."""
        with session_scope() as session:
            row = self._resolve_project(session, project_ref)
            if row is None:
                raise KeyError(f"Project not found: {project_ref}")
            new_name = self._clean(project)
            if new_name is not None and new_name != row.name:
                existing_name = session.scalar(select(Project).where(Project.name == new_name))
                if existing_name is not None and existing_name.id != row.id:
                    raise ValueError(f"Project already exists: {new_name}")
                row.name = new_name
                if project_slug is None:
                    project_slug = self._slugify(new_name)
            new_slug = self._clean(project_slug)
            if new_slug is not None and new_slug != row.slug:
                existing_slug = session.scalar(select(Project).where(Project.slug == new_slug))
                if existing_slug is not None and existing_slug.id != row.id:
                    raise ValueError(f"Project slug already exists: {new_slug}")
                row.slug = new_slug
            session.flush()
            return self._to_dict(row)

    def resolve_project(self, project_ref: str) -> dict[str, Any]:
        """Resolve one project by server id or slug."""
        with session_scope() as session:
            row = self._resolve_project(session, project_ref)
            if row is None:
                raise KeyError(f"Project not found: {project_ref}")
            return self._to_dict(row)

    @staticmethod
    def _resolve_project(session, project_ref: str | None) -> Project | None:
        """Resolve one project row by authoritative id or slug."""
        normalized = str(project_ref or "").strip()
        if not normalized:
            return None
        row = session.scalar(select(Project).where(Project.project_id == normalized))
        if row is not None:
            return row
        return session.scalar(select(Project).where(Project.slug == normalized.lower()))
