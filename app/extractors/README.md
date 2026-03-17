# Extractors

This directory contains the structured extraction pipeline for TRAQ sections. Each section has:

- `models.py` — Pydantic schema for the section
- `<section>.txt` — section prompt with field guidance
- `extractor.py` — thin wrapper that calls the registry

Common/shared logic lives in:
- `common.py` — OpenAI schema normalization + Outlines runner
- `system_common.txt` — shared system prompt for all extractors
- `registry.py` — central configuration and runner

## How extraction works

1) The server assembles a section transcript (per round).
2) The registry selects the model + prompt for the section.
3) `common.run_outlines_extraction()` builds the prompt:
   - system prompt (`system_common.txt`)
   - section instructions (`<section>.txt`)
   - transcript text
4) Outlines returns JSON that is validated by the Pydantic model.

## Registry purpose

`registry.py` centralizes all extractor configuration:
- section id
- model class
- section prompt filename
- system prompt (currently shared via `system_common.txt`)

It also provides a single entry point:

```python
run_extraction("site_factors", transcript)
```

This keeps extractors consistent and avoids duplicate wiring across the codebase.

## Adding a new extractor

1) Create a new folder under `app/extractors/<section_id>`
2) Add `models.py` with a Pydantic model (inherit `StrictBaseModel`)
3) Add `<section_id>.txt` prompt
4) Add `extractor.py` (thin wrapper):

```python
from typing import cast
from .models import MySectionExtraction
from ..registry import run_extraction


def run_my_section_extraction(transcript: str) -> MySectionExtraction:
    return cast(MySectionExtraction, run_extraction("my_section", transcript))
```

5) Register it in `registry.py`:

```python
"my_section": ExtractorConfig(
    section_id="my_section",
    model_cls=MySectionExtraction,
    section_prompt="my_section.txt",
    system_prompt=None,  # uses system_common.txt
),
```

6) Wire it in `app/main.py` where extraction happens (merge into `draft_form`).

## Notes

- All schemas are normalized for OpenAI JSON schema strictness in `common.py`.
- System prompt is shared across all extractors (`system_common.txt`).
- Section prompts should stay text‑only for easy iteration.
