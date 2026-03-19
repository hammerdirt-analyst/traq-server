"""Shared runtime dependency context for the FastAPI application."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any, Callable

from .artifact_storage import ArtifactStore, create_artifact_store
from .db_store import DatabaseStore
from .security_store import SecurityStore
from .service_discovery import DiscoveryConfig, ServiceDiscoveryAdvertiser
from .services.access_control_service import AccessControlService
from .services.customer_service import CustomerService
from .services.final_mutation_service import FinalMutationService
from .services.finalization_service import FinalizationService
from .services.job_mutation_service import JobMutationService
from .services.media_runtime_service import MediaRuntimeService
from .services.review_payload_service import ReviewPayloadService
from .services.review_form_service import ReviewFormService
from .services.round_submit_service import RoundSubmitService
from .services.runtime_state_service import RuntimeStateService

if TYPE_CHECKING:
    from .config import Settings


@dataclass
class RuntimeContext:
    """All shared runtime dependencies required by the HTTP entrypoint."""

    settings: "Settings"
    logger: logging.Logger
    jobs: dict[str, Any] = field(default_factory=dict)
    db_store: DatabaseStore = field(init=False)
    artifact_store: ArtifactStore = field(init=False)
    security: SecurityStore = field(init=False)
    access_control_service: AccessControlService = field(init=False)
    customer_service: CustomerService = field(init=False)
    final_mutation_service: FinalMutationService = field(init=False)
    finalization_service: FinalizationService = field(init=False)
    job_mutation_service: JobMutationService = field(init=False)
    media_runtime_service: MediaRuntimeService = field(init=False)
    review_payload_service: ReviewPayloadService = field(init=False)
    review_form_service: ReviewFormService = field(init=False)
    round_submit_service: RoundSubmitService = field(init=False)
    runtime_state_service: RuntimeStateService = field(init=False)
    advertiser: ServiceDiscoveryAdvertiser = field(init=False)

    def __post_init__(self) -> None:
        """Construct shared services once for the application runtime."""
        self.db_store = DatabaseStore()
        self.artifact_store = create_artifact_store(self.settings)
        self.security = SecurityStore(self.settings.storage_root / "security")
        self.access_control_service = AccessControlService(
            api_key=self.settings.api_key,
            db_store=self.db_store,
            logger=self.logger,
        )
        self.customer_service = CustomerService()
        self.final_mutation_service = FinalMutationService()
        self.finalization_service = FinalizationService()
        self.job_mutation_service = JobMutationService()
        self.media_runtime_service = MediaRuntimeService(
            db_store=self.db_store,
            artifact_store=self.artifact_store,
            logger=self.logger,
        )
        self.review_payload_service = ReviewPayloadService()
        self.review_form_service = ReviewFormService()
        self.round_submit_service = RoundSubmitService()
        self.advertiser = ServiceDiscoveryAdvertiser(
            DiscoveryConfig(
                port=self.settings.discovery_port,
                service_name=self.settings.discovery_name,
            ),
            logger=self.logger,
        )

    def bind_runtime_state_service(
        self,
        *,
        parse_tree_number: Callable[[Any], int | None],
        job_record_factory: Callable[..., Any],
        round_record_factory: Callable[..., Any],
        write_json: Callable[[Any, dict[str, Any]], None],
    ) -> None:
        """Attach runtime-state helper once main has defined its local models/helpers."""
        self.runtime_state_service = RuntimeStateService(
            storage_root=self.settings.storage_root,
            db_store=self.db_store,
            artifact_store=self.artifact_store,
            logger=self.logger,
            parse_tree_number=parse_tree_number,
            job_record_factory=job_record_factory,
            round_record_factory=round_record_factory,
            write_json=write_json,
        )
