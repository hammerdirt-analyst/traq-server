# Server App README

## Purpose
The purpose of this server is to process field notes and observations to make standard reports (forms) and qualitative summaries for tree inventories and urban forestry.

It is designed to be used by one person or a small team.

The server extracts data from audio and video sources provided by the client app.

## What This Service Does
- Accepts section-level recordings and images from the mobile client.
- Transcribes uploaded recordings.
- Runs structured extraction per section (extractor registry).
- Merges extracted data and user form edits into the review form state.
- Returns review payloads for iterative correction.
- Generates final TRAQ PDF and report letter PDF.
- Generates `final.geojson` from final form data for map/export workflows.

## Persistence Direction

- PostgreSQL is the intended metadata/state store.
- The current filesystem layout remains in use for artifacts:
  - uploaded audio
  - uploaded images
  - generated PDFs/DOCX
  - exported GeoJSON
- The database migration is intended to replace filesystem metadata/state, not
  binary artifact storage.

Recommended database URL:

- `postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo`

Bootstrap notes are tracked in:

- `docs/postgresql_bootstrap.md`
- `docs/database_schema.rst`

## Current Processing Flow
1. Client creates a round.
2. Client uploads recordings/images by section.
3. Client sends round manifest.
4. Client submits round (optional form patch included).
5. Server transcribes recordings.
6. Server runs section extractors.
7. Server merges extraction + edits into `draft_form.data`.
8. Server returns review payload.
9. Final submit generates TRAQ + report PDFs.

### Managed context through granular recordings
- Extraction accuracy is driven by section-scoped recordings.
- Context is carried by recording label (client-selected section) and can also be reinforced by spoken context in audio.
- Server processes recordings in that scoped context, rather than one large mixed transcript.
- Tradeoff: more backend/API calls (often one upload call per recording), in exchange for higher extraction precision and less manual correction time.

## Key Modules
- `main.py`: FastAPI endpoints, round/review lifecycle, merge logic.
- `extractors/`: section extractor models/prompts/registry wiring.
- `pdf_fill.py`: overlay-only TRAQ PDF generation using `app/traq_2_schema/traq_full_map.json`.
- `report_letter.py`: summary/report letter generation and PDF output.
- `geojson_export.py`: public-map GeoJSON export (`final.geojson`) from scrubbed form data.

## Mapping and PDF Fill
- Runtime map source: `app/traq_2_schema/traq_full_map.json`.
- Fill mode: visual overlay (no AcroForm dependency in runtime path).
- Canonical semantic sources:
  - `app/traq_2_schema/mapone.md`
  - `app/traq_2_schema/maptwo.md`

## API Surface (Core)
- `POST /v1/jobs`
- `PATCH /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/assigned`
- `GET /v1/projects`
- `POST /v1/jobs/{job_id}/rounds`
- `PUT /v1/jobs/{job_id}/rounds/{round_id}/manifest`
- `POST /v1/jobs/{job_id}/rounds/{round_id}/submit`
- `POST /v1/jobs/{job_id}/rounds/{round_id}/reprocess`
- `GET /v1/jobs/{job_id}/rounds/{round_id}/review`
- `POST /v1/jobs/{job_id}/final`
- `GET /v1/jobs/{job_id}/final/report`

## Device Auth and Roles

Auth model:
- No passwords.
- Device registration + admin approval.
- Device tokens (default TTL currently 7 days).

Roles:
- `arborist`: standard data collection and submission.
- `admin`: full access, device approval/revoke, round reopen.

Job assignment rules:
- Arborist devices can only see and edit jobs explicitly assigned to that device.
- A job can be assigned to only one device at a time.
- Reassigning a job moves ownership to the new device immediately.
- Admin can always reassign/unassign jobs.
- `GET /v1/jobs/assigned` returns only assigned jobs (no automatic global job push).
- Jobs created by an arborist device are auto-assigned to that same device.
- There are no preloaded jobs in runtime; jobs are initiated from client submissions.
- Assigned device clients can update job metadata through `PATCH /v1/jobs/{job_id}`.
- Metadata updates currently cover `project_id`, `job_name`, `job_address`, and `location_notes`.
- Metadata updates are allowed in `DRAFT` and after review returns.
- Metadata updates are blocked while a round is `SUBMITTED_FOR_PROCESSING`.
- Archived jobs still require admin reopen before device-side edits.

Auth endpoints:
- `POST /v1/auth/register-device`
- `GET /v1/auth/device/{device_id}/status`
- `POST /v1/auth/token`
- `GET /v1/projects`

Admin endpoints:
- `GET /v1/admin/devices`
- `GET /v1/admin/devices/pending`
- `POST /v1/admin/devices/{device_id}/approve`
- `POST /v1/admin/devices/{device_id}/revoke`
- `POST /v1/admin/devices/{device_id}/issue-token`
- `POST /v1/admin/jobs/{job_id}/rounds/{round_id}/reopen`
- `GET /v1/admin/jobs/assignments`
- `GET /v1/admin/jobs/resolve`
- `POST /v1/admin/jobs/{job_id}/assign`
- `POST /v1/admin/jobs/{job_id}/unassign`
- `POST /v1/admin/jobs/{job_id}/status`
- `GET /v1/admin/jobs/{job_id}/inspect`
- `GET /v1/admin/jobs/{job_id}/rounds/{round_id}/inspect`
- `GET /v1/admin/jobs/{job_id}/rounds/{round_id}/review/inspect`
- `GET /v1/admin/jobs/{job_id}/final/inspect`
- `GET /v1/admin/jobs/{job_id}/artifacts/{kind}`

Credential transport:
- Existing `x-api-key` header now accepts either:
  - server admin API key (`TRAQ_API_KEY`)
  - issued device token

Standalone tree identification:
- `POST /v1/trees/identify`
- independent of jobs and rounds
- authenticated through the normal server auth path

## Admin CLI

Use `traq-admin` for operator workflows. The detailed user guide lives in
`docs/cli_operations_model.rst`; this README keeps only the current shape and
the most common commands.

Two execution modes matter:

- `uv run traq-admin local`
  - local operator mode
  - uses local services and the configured database
- `uv run traq-admin cloud`
  - remote operator mode
  - uses `TRAQ_CLOUD_ADMIN_BASE_URL` and `TRAQ_CLOUD_API_KEY`
  - talks to the deployed server over HTTP only

Mode rule:

- local mode must not silently switch to remote HTTP
- cloud mode must not silently inspect local DB state or files
- unsupported cloud commands should fail explicitly

Interactive shell:

```bash
uv run traq-admin cloud
```

Useful meta-commands:

```text
show
use local
use cloud
set host https://example.run.app
set api-key <admin_key>
exit
```

Covered command groups:

- device admin
- customer and billing admin
- project admin
- job create, update, assignment, status, and inspect
- round create, manifest get/set, submit, reprocess, inspect, and reopen
- review inspect
- final inspect and artifact fetch
- export sync and artifact fetch for downstream reporting clients
- standalone tree identification

Current limits:

- `final set-final` and `final set-correction` are not part of the current
  cloud parity path
- local mode does not yet implement `round submit` or `round reprocess`

Examples:

```bash
# Device and job inspection
uv run traq-admin cloud device pending
uv run traq-admin cloud customer list --search Arboretum
uv run traq-admin cloud project list
uv run traq-admin cloud job inspect --job J0001

# Project assignment
uv run traq-admin cloud project create --project "Briarwood"
uv run traq-admin cloud job update --job J0001 --project-id project_abc123

# Round lifecycle
uv run traq-admin cloud round create --job J0001
uv run traq-admin cloud round manifest set --job J0001 --round-id round_1 --file ./manifest_smoke.json
uv run traq-admin cloud round manifest get --job J0001 --round-id round_1

# Submit and reprocess
uv run traq-admin cloud round submit --job J0001 --round-id round_1 --file ./templates/round_submit.template.json
uv run traq-admin cloud round reprocess --job J0001 --round-id round_1

# Review and final inspection
uv run traq-admin cloud review inspect --job J0001 --round-id round_1
uv run traq-admin cloud final inspect --job J0001
uv run traq-admin cloud artifact fetch --job J0001 --kind final-json
uv run traq-admin cloud artifact fetch --job J0001 --kind geo-json

# Export sync for downstream reporting clients
uv run traq-admin cloud export changes
uv run traq-admin cloud export changes --cursor 2026-03-24T18:45:00Z
uv run traq-admin cloud export image-fetch --job-id job_123 --image-ref img_1 --variant report
uv run traq-admin cloud export images-fetch-all --job J0001 --variant report
uv run traq-admin cloud export geojson-fetch --job-id job_456

# Standalone tree identification
uv run traq-admin cloud tree identify --image ./bark.jpg
```

Export notes:

- run export commands from `server/`
- use the same admin cloud configuration as other remote CLI commands
- `export changes` returns the current sync payload with `in_process`, `completed`, and `transitioned_to_completed`
- `export image-fetch` downloads one image referenced by the export payload
- `export images-fetch-all` resolves all export-visible image refs for one job and downloads them in one command
- `export geojson-fetch` downloads archived GeoJSON for a completed job

Smoke-test helpers kept in this repo:

- `manifest_smoke.json`
- `templates/round_submit.template.json`

Use `manifest_smoke.json` as a minimal manifest fixture for `round manifest set`.
Copy `templates/round_submit.template.json` to a working file, edit it for the
test case, and pass that file to `round submit --file ...`.

## Storage
- Job artifacts and exported debug copies: `local_data/jobs/...`
- Logs: `local_data/logs/...`
- Exported review payload: `review.json` per round
- Final outputs: job-level final PDFs, `final.json`, and `final.geojson`

## Public Map Export
- `final.geojson` is for public-map use.
- It includes only:
  - `job_number`
  - `user_name`
  - scrubbed `form_data`
  - image captions/timestamps
- Client-identifying fields are removed from `client_tree_details` in exported `form_data`.

## Audio Guidance (Integrated)
Reference: tracked as an internal documentation migration follow-up.

Operational guidance used in this project:
- Prefer Android capture at PCM 16-bit, mono, 16 kHz.
- Prefer `VOICE_RECOGNITION` source (or `UNPROCESSED` when available).
- Disable AGC/NS/AEC where supported.
- Keep server-side transcription input normalized/consistent.
- Log audio metadata (codec, sample rate, channels, duration) for diagnosis.

## Network Guidance (Integrated)
Reference: tracked as an internal documentation migration follow-up.

Operational guidance used in this project:
- Use `--host 0.0.0.0` for IPv4 LAN testing.
- Use `--host ::` for IPv6-only or dual-stack environments.
- Validate bind with:
  - `ss -ltnp | rg 8000`
- Validate health endpoint from server host and from device.
- For IPv6 client URLs, use bracket syntax: `http://[<ipv6>]:8000`.

## Running the Server
Example (current common local run):

```bash
TRAQ_LOG_RAW_TRANSCRIPTS=1 \
TRAQ_FFPROBE_BIN="$(command -v ffprobe)" \
uv run traq-server --reload --host 0.0.0.0 --port 8000 --log-level debug
```

IPv6 variant:

```bash
TRAQ_LOG_RAW_TRANSCRIPTS=1 \
TRAQ_FFPROBE_BIN="$(command -v ffprobe)" \
uv run traq-server --reload --host :: --port 8000 --log-level debug
```

## Notes for Developers
- Keep extractor output schema aligned with canonical map semantics in `app/traq_2_schema/mapone.md` and `app/traq_2_schema/maptwo.md`.
- Keep `traq_full_map.json` as the single runtime mapping source for fill.
- Do not reintroduce AcroForm-only mapping paths for runtime PDF generation.
