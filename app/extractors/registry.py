"""Extractor registry and section dispatch for structured extraction.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Centralize section-to-model/prompt wiring and expose one canonical
    `run_extraction(section_id, transcript)` entrypoint used by server runtime.

Design:
    - `EXTRACTOR_CONFIG` maps section ids to model classes and prompt files.
    - A shared system prompt (`system_common.txt`) is used by default.
    - Dispatch delegates execution to `common.run_outlines_extraction(...)`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from .common import run_outlines_extraction
from .client_tree_details.models import ClientTreeDetailsExtraction
from .site_factors.models import SiteFactorsExtraction
from .tree_health_and_species.models import TreeHealthAndSpeciesExtraction
from .load_factors.models import LoadFactorsExtraction
from .crown_and_branches.models import CrownAndBranchesExtraction
from .trunk.models import TrunkExtraction
from .roots_and_root_collar.models import RootsAndRootCollarExtraction
from .target_assessment.models import TargetAssessmentExtraction
from .risk_categorization.models import RiskCategorizationExtraction
from .notes_explanations_descriptions.models import (
    NotesExplanationsDescriptionsExtraction,
)
from .mitigation_options.models import MitigationOptionsExtraction
from .overall_tree_risk_rating.models import OverallTreeRiskRatingExtraction
from .work_priority.models import WorkPriorityExtraction
from .overall_residual_risk.models import OverallResidualRiskExtraction
from .recommended_inspection_interval.models import (
    RecommendedInspectionIntervalExtraction,
)
from .data_status.models import DataStatusExtraction
from .advanced_assessment_needed.models import AdvancedAssessmentNeededExtraction
from .advanced_assessment_type_reason.models import (
    AdvancedAssessmentTypeReasonExtraction,
)
from .inspection_limitations.models import InspectionLimitationsExtraction
from .inspection_limitations_describe.models import (
    InspectionLimitationsDescribeExtraction,
)


@dataclass(frozen=True)
class ExtractorConfig:
    """Static registry row describing one section extractor contract.

    Attributes:
        section_id: Canonical section key.
        model_cls: Pydantic model class expected from extraction.
        section_prompt: Prompt filename under section directory.
        system_prompt: Optional section-specific system prompt filename.
            If `None`, registry uses `system_common.txt`.
    """

    section_id: str
    model_cls: Type[BaseModel]
    section_prompt: str
    system_prompt: str | None = None


BASE_DIR = Path(__file__).resolve().parent
COMMON_SYSTEM_PATH = BASE_DIR / "system_common.txt"

EXTRACTOR_CONFIG: dict[str, ExtractorConfig] = {
    "client_tree_details": ExtractorConfig(
        section_id="client_tree_details",
        model_cls=ClientTreeDetailsExtraction,
        section_prompt="client_tree_details.txt",
        system_prompt=None,
    ),
    "site_factors": ExtractorConfig(
        section_id="site_factors",
        model_cls=SiteFactorsExtraction,
        section_prompt="site_factors.txt",
        system_prompt=None,
    ),
    "tree_health_and_species": ExtractorConfig(
        section_id="tree_health_and_species",
        model_cls=TreeHealthAndSpeciesExtraction,
        section_prompt="tree_health_and_species.txt",
        system_prompt=None,
    ),
    "load_factors": ExtractorConfig(
        section_id="load_factors",
        model_cls=LoadFactorsExtraction,
        section_prompt="load_factors.txt",
        system_prompt=None,
    ),
    "crown_and_branches": ExtractorConfig(
        section_id="crown_and_branches",
        model_cls=CrownAndBranchesExtraction,
        section_prompt="crown_and_branches.txt",
        system_prompt=None,
    ),
    "trunk": ExtractorConfig(
        section_id="trunk",
        model_cls=TrunkExtraction,
        section_prompt="trunk.txt",
        system_prompt=None,
    ),
    "roots_and_root_collar": ExtractorConfig(
        section_id="roots_and_root_collar",
        model_cls=RootsAndRootCollarExtraction,
        section_prompt="roots_and_root_collar.txt",
        system_prompt=None,
    ),
    "target_assessment": ExtractorConfig(
        section_id="target_assessment",
        model_cls=TargetAssessmentExtraction,
        section_prompt="target_assessment.txt",
        system_prompt=None,
    ),
    "risk_categorization": ExtractorConfig(
        section_id="risk_categorization",
        model_cls=RiskCategorizationExtraction,
        section_prompt="risk_categorization.txt",
        system_prompt=None,
    ),
    "notes_explanations_descriptions": ExtractorConfig(
        section_id="notes_explanations_descriptions",
        model_cls=NotesExplanationsDescriptionsExtraction,
        section_prompt="notes_explanations_descriptions.txt",
        system_prompt=None,
    ),
    "mitigation_options": ExtractorConfig(
        section_id="mitigation_options",
        model_cls=MitigationOptionsExtraction,
        section_prompt="mitigation_options.txt",
        system_prompt=None,
    ),
    "overall_tree_risk_rating": ExtractorConfig(
        section_id="overall_tree_risk_rating",
        model_cls=OverallTreeRiskRatingExtraction,
        section_prompt="overall_tree_risk_rating.txt",
        system_prompt=None,
    ),
    "work_priority": ExtractorConfig(
        section_id="work_priority",
        model_cls=WorkPriorityExtraction,
        section_prompt="work_priority.txt",
        system_prompt=None,
    ),
    "overall_residual_risk": ExtractorConfig(
        section_id="overall_residual_risk",
        model_cls=OverallResidualRiskExtraction,
        section_prompt="overall_residual_risk.txt",
        system_prompt=None,
    ),
    "recommended_inspection_interval": ExtractorConfig(
        section_id="recommended_inspection_interval",
        model_cls=RecommendedInspectionIntervalExtraction,
        section_prompt="recommended_inspection_interval.txt",
        system_prompt=None,
    ),
    "data_status": ExtractorConfig(
        section_id="data_status",
        model_cls=DataStatusExtraction,
        section_prompt="data_status.txt",
        system_prompt=None,
    ),
    "advanced_assessment_needed": ExtractorConfig(
        section_id="advanced_assessment_needed",
        model_cls=AdvancedAssessmentNeededExtraction,
        section_prompt="advanced_assessment_needed.txt",
        system_prompt=None,
    ),
    "advanced_assessment_type_reason": ExtractorConfig(
        section_id="advanced_assessment_type_reason",
        model_cls=AdvancedAssessmentTypeReasonExtraction,
        section_prompt="advanced_assessment_type_reason.txt",
        system_prompt=None,
    ),
    "inspection_limitations": ExtractorConfig(
        section_id="inspection_limitations",
        model_cls=InspectionLimitationsExtraction,
        section_prompt="inspection_limitations.txt",
        system_prompt=None,
    ),
    "inspection_limitations_describe": ExtractorConfig(
        section_id="inspection_limitations_describe",
        model_cls=InspectionLimitationsDescribeExtraction,
        section_prompt="inspection_limitations_describe.txt",
        system_prompt=None,
    ),
}


def run_extraction(section_id: str, transcript: str) -> BaseModel:
    """Run extractor dispatch for a section transcript.

    Args:
        section_id: Section key to resolve in `EXTRACTOR_CONFIG`.
        transcript: Transcript text for that section.

    Returns:
        Parsed Pydantic model instance for the configured section.

    Raises:
        KeyError: Unknown/unregistered section id.
        ValueError: Empty transcript (raised by common runtime).
        RuntimeError: Missing API key/model configuration.
    """
    config = EXTRACTOR_CONFIG.get(section_id)
    if not config:
        raise KeyError(f"Unknown extractor section: {section_id}")

    base_dir = BASE_DIR / section_id
    system_path = (
        base_dir / config.system_prompt
        if config.system_prompt is not None
        else COMMON_SYSTEM_PATH
    )
    section_path = base_dir / config.section_prompt

    logger = logging.getLogger(f"traq_demo.extractor.{section_id}")
    return run_outlines_extraction(
        transcript=transcript,
        model_cls=config.model_cls,
        system_path=system_path,
        section_path=section_path,
        logger=logger,
    )
