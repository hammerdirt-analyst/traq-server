"""Initial PostgreSQL ORM models for the TRAQ server.

Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

The schema is split into two categories:
- permanent records: devices, jobs, finals, artifacts, audit events
- working records: rounds and uploaded media metadata

Artifacts such as audio, images, PDFs, DOCX, and GeoJSON remain on disk. These
models store identifiers, workflow state, and paths to those artifacts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


UUID_TYPE = Uuid(as_uuid=True)
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamps for model defaults."""

    return datetime.now(timezone.utc)


class DeviceStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    revoked = "revoked"


class DeviceRole(str, Enum):
    arborist = "arborist"
    admin = "admin"


class JobStatus(str, Enum):
    not_started = "NOT_STARTED"
    draft = "DRAFT"
    submitted = "SUBMITTED_FOR_PROCESSING"
    review_returned = "REVIEW_RETURNED"
    archived = "ARCHIVED"
    failed = "FAILED"


class RoundStatus(str, Enum):
    draft = "DRAFT"
    submitted = "SUBMITTED_FOR_PROCESSING"
    review_returned = "REVIEW_RETURNED"
    failed = "FAILED"


class UploadStatus(str, Enum):
    pending = "pending"
    uploading = "uploading"
    uploaded = "uploaded"
    processed = "processed"
    failed = "failed"


class ArtifactKind(str, Enum):
    audio = "audio"
    image = "image"
    transcript_txt = "transcript_txt"
    review_json = "review_json"
    final_json = "final_json"
    final_pdf = "final_pdf"
    report_pdf = "report_pdf"
    report_docx = "report_docx"
    geojson = "geojson"


class EventType(str, Enum):
    device_registered = "device_registered"
    device_approved = "device_approved"
    token_issued = "token_issued"
    job_created = "job_created"
    job_assigned = "job_assigned"
    round_created = "round_created"
    round_submitted = "round_submitted"
    round_reprocessed = "round_reprocessed"
    review_returned = "review_returned"
    final_generated = "final_generated"
    correction_generated = "correction_generated"
    status_changed = "status_changed"


class Device(Base):
    """Registered mobile or admin device known to the server."""

    __tablename__ = "devices"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[DeviceRole] = mapped_column(SqlEnum(DeviceRole), default=DeviceRole.arborist)
    status: Mapped[DeviceStatus] = mapped_column(SqlEnum(DeviceStatus), default=DeviceStatus.pending, index=True)
    profile_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tokens: Mapped[list[DeviceToken]] = relationship(back_populates="device", cascade="all, delete-orphan")
    assignments: Mapped[list[JobAssignment]] = relationship(back_populates="device")


class DeviceToken(Base):
    """Issued bearer token for an approved device."""

    __tablename__ = "device_tokens"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    device_id: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    role: Mapped[DeviceRole] = mapped_column(SqlEnum(DeviceRole))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    device: Mapped[Device] = relationship(back_populates="tokens")


class RuntimeProfile(Base):
    """DB-authoritative runtime profile bound to one auth identity.

    This replaces the older file-backed profile JSON as the source of truth for
    runtime reads and writes. A filesystem copy may still be exported for
    debugging, but it is not authoritative.
    """

    __tablename__ = "runtime_profiles"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    identity_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    profile_payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RuntimeCounter(Base):
    """DB-authoritative monotonic counters used for runtime identifiers.

    These counters replace older local filesystem counter files so multi-instance
    deployments can allocate identifiers safely inside one transactional store.
    """

    __tablename__ = "runtime_counters"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    counter_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    current_value: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Customer(Base):
    """Reusable customer/contact identity referenced by one or more jobs."""

    __tablename__ = "customers"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    customer_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    trees: Mapped[list[Tree]] = relationship(back_populates="customer")
    jobs: Mapped[list[Job]] = relationship(back_populates="customer")


class BillingProfile(Base):
    """Reusable billing identity referenced by one or more jobs."""

    __tablename__ = "billing_profiles"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    billing_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    billing_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    billing_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    jobs: Mapped[list[Job]] = relationship(back_populates="billing_profile")


class Operator(Base):
    """Reusable assessor/operator identity derived from final output provenance."""

    __tablename__ = "operators"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    jobs: Mapped[list[Job]] = relationship(back_populates="operator")


class Tree(Base):
    """Reusable customer-scoped tree identity shared by multiple jobs."""

    __tablename__ = "trees"
    __table_args__ = (
        UniqueConstraint("customer_id", "tree_number", name="uq_trees_customer_tree_number"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    customer_id: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    tree_number: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="trees")
    jobs: Mapped[list[Job]] = relationship(back_populates="tree")


class Job(Base):
    """Top-level job record and current workflow status."""

    __tablename__ = "jobs"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    job_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    job_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[PyUUID | None] = mapped_column(UUID_TYPE, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    billing_profile_id: Mapped[PyUUID | None] = mapped_column(UUID_TYPE, ForeignKey("billing_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    operator_id: Mapped[PyUUID | None] = mapped_column(UUID_TYPE, ForeignKey("operators.id", ondelete="SET NULL"), nullable=True, index=True)
    tree_id: Mapped[PyUUID | None] = mapped_column(UUID_TYPE, ForeignKey("trees.id", ondelete="SET NULL"), nullable=True, index=True)
    tree_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    job_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tree_species: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[JobStatus] = mapped_column(SqlEnum(JobStatus), default=JobStatus.draft, index=True)
    latest_round_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latest_round_status: Mapped[RoundStatus | None] = mapped_column(SqlEnum(RoundStatus), nullable=True)
    profile_identity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    final_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    correction_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer | None] = relationship(back_populates="jobs")
    billing_profile: Mapped[BillingProfile | None] = relationship(back_populates="jobs")
    operator: Mapped[Operator | None] = relationship(back_populates="jobs")
    tree: Mapped[Tree | None] = relationship(back_populates="jobs")
    assignments: Mapped[list[JobAssignment]] = relationship(back_populates="job", cascade="all, delete-orphan")
    rounds: Mapped[list[JobRound]] = relationship(back_populates="job", cascade="all, delete-orphan")
    finals: Mapped[list[JobFinal]] = relationship(back_populates="job", cascade="all, delete-orphan")
    geojson_exports: Mapped[list[JobGeoJSONExport]] = relationship(back_populates="job", cascade="all, delete-orphan")
    events: Mapped[list[JobEvent]] = relationship(back_populates="job", cascade="all, delete-orphan")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobAssignment(Base):
    """Current device assignment for a job.

    A job may be assigned to only one device at a time.
    """

    __tablename__ = "job_assignments"
    __table_args__ = (UniqueConstraint("job_id", name="uq_job_assignments_job_id"),)

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    job_id: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("devices.id", ondelete="RESTRICT"), index=True)
    assigned_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="assignments")
    device: Mapped[Device] = relationship(back_populates="assignments")


class JobRound(Base):
    """Working review round for a job.

    These are intended as transient records and can be pruned after archival if
    the final/correction snapshots and audit trail are preserved.
    """

    __tablename__ = "job_rounds"
    __table_args__ = (
        UniqueConstraint("job_id", "round_id", name="uq_job_rounds_job_round_id"),
        Index("ix_job_rounds_job_status", "job_id", "status"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    job_id: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    round_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[RoundStatus] = mapped_column(SqlEnum(RoundStatus), default=RoundStatus.draft, index=True)
    server_revision_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manifest: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, default=list)
    review_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="rounds")
    recordings: Mapped[list[RoundRecording]] = relationship(back_populates="round", cascade="all, delete-orphan")
    images: Mapped[list[RoundImage]] = relationship(back_populates="round", cascade="all, delete-orphan")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="round", cascade="all, delete-orphan")


class RoundRecording(Base):
    """Metadata for one uploaded recording associated with a round."""

    __tablename__ = "round_recordings"
    __table_args__ = (
        UniqueConstraint("round_pk", "recording_id", name="uq_round_recordings_round_recording_id"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    round_pk: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("job_rounds.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[str] = mapped_column(String(128), index=True)
    recording_id: Mapped[str] = mapped_column(String(255), index=True)
    upload_status: Mapped[UploadStatus] = mapped_column(SqlEnum(UploadStatus), default=UploadStatus.pending, index=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    round: Mapped[JobRound] = relationship(back_populates="recordings")


class RoundImage(Base):
    """Metadata for one uploaded image associated with a round."""

    __tablename__ = "round_images"
    __table_args__ = (
        UniqueConstraint("round_pk", "image_id", name="uq_round_images_round_image_id"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    round_pk: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("job_rounds.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[str] = mapped_column(String(128), index=True)
    image_id: Mapped[str] = mapped_column(String(255), index=True)
    upload_status: Mapped[UploadStatus] = mapped_column(SqlEnum(UploadStatus), default=UploadStatus.pending, index=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[str | None] = mapped_column(String(64), nullable=True)
    longitude: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    round: Mapped[JobRound] = relationship(back_populates="images")


class JobFinal(Base):
    """Immutable final or overwriteable correction snapshot for a job."""

    __tablename__ = "job_finals"
    __table_args__ = (
        UniqueConstraint("job_id", "kind", name="uq_job_finals_job_kind"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    job_id: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    round_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="finals")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="final", cascade="all, delete-orphan")


class JobGeoJSONExport(Base):
    """Stored GeoJSON export object linked to a job and export kind."""

    __tablename__ = "job_geojson_exports"
    __table_args__ = (
        UniqueConstraint("job_id", "kind", name="uq_job_geojson_exports_job_kind"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    job_id: Mapped[PyUUID] = mapped_column(UUID_TYPE, ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="geojson_exports")


class Artifact(Base):
    """Reference to a generated or uploaded artifact kept outside the database."""

    __tablename__ = "artifacts"

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    job_id: Mapped[PyUUID | None] = mapped_column(UUID_TYPE, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    round_pk: Mapped[PyUUID | None] = mapped_column(UUID_TYPE, ForeignKey("job_rounds.id", ondelete="CASCADE"), nullable=True, index=True)
    job_final_id: Mapped[PyUUID | None] = mapped_column(UUID_TYPE, ForeignKey("job_finals.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[ArtifactKind] = mapped_column(SqlEnum(ArtifactKind), index=True)
    path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[Job | None] = relationship(back_populates="artifacts")
    round: Mapped[JobRound | None] = relationship(back_populates="artifacts")
    final: Mapped[JobFinal | None] = relationship(back_populates="artifacts")


class JobEvent(Base):
    """Append-only audit/event record for job and device workflow transitions."""

    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_created", "job_id", "created_at"),)

    id: Mapped[PyUUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid4)
    job_id: Mapped[PyUUID | None] = mapped_column(UUID_TYPE, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type: Mapped[EventType] = mapped_column(SqlEnum(EventType), index=True)
    actor_identity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[Job | None] = relationship(back_populates="events")
