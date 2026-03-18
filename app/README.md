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

Auth endpoints:
- `POST /v1/auth/register-device`
- `GET /v1/auth/device/{device_id}/status`
- `POST /v1/auth/token`

Admin endpoints:
- `POST /v1/admin/jobs/{job_id}/rounds/{round_id}/reopen`
- `GET /v1/admin/jobs/assignments`
- `POST /v1/admin/jobs/{job_id}/assign`
- `POST /v1/admin/jobs/{job_id}/unassign`
- `POST /v1/admin/jobs/{job_id}/status`

Credential transport:
- Existing `x-api-key` header now accepts either:
  - server admin API key (`TRAQ_API_KEY`)
  - issued device token

Admin CLI (host machine):
- `export TRAQ_DATABASE_URL='postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo'`
- `uv run traq-admin device pending`
- `uv run traq-admin device validate --index 1 --role arborist`
- `uv run traq-admin device approve <device_id> --role arborist`
- `uv run traq-admin device revoke <device_id>`
- `uv run traq-admin device issue-token <device_id> --ttl 900`
- `uv run traq-admin customer create --name "Customer Name" --phone "555-1212" --address "123 Oak St"`
- `uv run traq-admin customer list --search Arboretum`
- `uv run traq-admin customer update C0001 --phone "555-3434"`
- `uv run traq-admin customer billing create --billing-name "Customer Name" --billing-address "123 Oak St"`
- `uv run traq-admin customer billing list --search Customer`
- `uv run traq-admin customer billing update B0001 --contact-preference email`
- `uv run traq-admin job create --job-id job_1 --job-number J0001 --customer-id C0001 --billing-profile-id B0001 --tree-number 1 --job-name "Valley Oak"`
- `uv run traq-admin job update --job J0001 --customer-id C0001 --billing-profile-id B0001 --tree-number 2 --job-name "Valley Oak Revisit" --status REVIEW_RETURNED`
- `uv run traq-admin final set-final --job J0001 --from-json ./final.json [--geojson-json ./final.geojson]`
- `uv run traq-admin final set-correction --job J0001 --from-json ./final_correction.json [--geojson-json ./final_correction.geojson]`
- `uv run traq-admin job assign --job J0001 --device-id <device_id> --host http://127.0.0.1:8000 --api-key <admin_key>`
- `uv run traq-admin job unassign --job J0001 --host http://127.0.0.1:8000 --api-key <admin_key>`
- `uv run traq-admin job list-assignments --host http://127.0.0.1:8000 --api-key <admin_key>`
- `uv run traq-admin job set-status --job J0001 --status DRAFT --host http://127.0.0.1:8000 --api-key <admin_key>`
- `uv run traq-admin job inspect --job J0001`
- `uv run traq-admin round reopen --job-id <job_id> --round-id <round_id> --host http://127.0.0.1:8000 --api-key <admin_key>`
- `uv run traq-admin round inspect --job J0001 --round-id <round_id>`
- `uv run traq-admin review inspect --job J0001 --round-id <round_id>`
- `uv run traq-admin final inspect --job J0001`

### Admin CLI Usage

Start interactive CLI:

```bash
export TRAQ_DATABASE_URL='postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo'
uv run traq-admin
```

Interactive meta-commands:

```text
help
show
set host http://127.0.0.1:8000
set api-key demo-key
exit
```

Inside interactive mode, operational commands accept the same syntax as the
one-shot CLI. A leading `/` is optional, so both `round inspect --job J0001
--round-id round_1` and `/round inspect --job J0001 --round-id round_1` work.

Required environment:

```bash
export TRAQ_DATABASE_URL='postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo'
export TRAQ_ADMIN_BASE_URL='http://127.0.0.1:8000'
```

For local operator workflows, `.env` is loaded automatically by
`app/config.py`. Shell exports still win if both are present.

The CLI now fails fast if ``TRAQ_DATABASE_URL`` is not set. There is no silent
SQLite fallback. HTTP-backed CLI commands now default to
``TRAQ_ADMIN_BASE_URL`` and ``TRAQ_API_KEY`` from settings, so ``--host`` and
``--api-key`` are optional unless you need to override them for a specific
command.

### Admin CLI Command Reference (all commands)

Device commands:

```bash
uv run traq-admin device list [--status pending|approved|revoked] [--json]
uv run traq-admin device pending [--json]
uv run traq-admin device validate [--index N] [--role arborist|admin]
uv run traq-admin device approve <device_id> [--role arborist|admin]
uv run traq-admin device revoke <device_id>
uv run traq-admin device issue-token <device_id> [--ttl 900]
```

Customer commands:

```bash
uv run traq-admin customer list [--search <term>]
uv run traq-admin customer duplicates
uv run traq-admin customer create --name <customer_name> [--phone <phone>] [--address <address>]
uv run traq-admin customer update <customer_id_or_code> [--name <customer_name>] [--phone <phone>] [--address <address>]
uv run traq-admin customer usage <customer_id_or_code>
uv run traq-admin customer merge <source_customer_id_or_code> --into <target_customer_id_or_code>
uv run traq-admin customer delete <customer_id_or_code>
uv run traq-admin customer billing list [--search <term>]
uv run traq-admin customer billing duplicates
uv run traq-admin customer billing create [--billing-name <name>] [--billing-contact-name <name>] [--billing-address <address>] [--contact-preference <pref>]
uv run traq-admin customer billing update <billing_profile_id_or_code> [--billing-name <name>] [--billing-contact-name <name>] [--billing-address <address>] [--contact-preference <pref>]
uv run traq-admin customer billing usage <billing_profile_id_or_code>
uv run traq-admin customer billing merge <source_billing_profile_id_or_code> --into <target_billing_profile_id_or_code>
uv run traq-admin customer billing delete <billing_profile_id_or_code>
```

Job commands:

```bash
uv run traq-admin job create --job-id <job_id> --job-number <job_number> [--customer-id <customer_id_or_code>] [--billing-profile-id <billing_profile_id_or_code>] [--tree-number <tree_number>] [--job-name <job_name>] [--job-address <address>] [--reason <reason>] [--location-notes <notes>] [--tree-species <species>] [--status ...]
uv run traq-admin job update --job <job_id_or_job_number> [--customer-id <customer_id_or_code>] [--billing-profile-id <billing_profile_id_or_code>] [--tree-number <tree_number>] [--job-name <job_name>] [--job-address <address>] [--reason <reason>] [--location-notes <notes>] [--tree-species <species>] [--status ...]
uv run traq-admin job list-assignments [--host <admin_base_url>] [--api-key <admin_key>] [--raw]
uv run traq-admin job assign --job <job_id_or_job_number> --device-id <device_id> [--host <admin_base_url>] [--api-key <admin_key>]
uv run traq-admin job unassign --job <job_id_or_job_number> [--host <admin_base_url>] [--api-key <admin_key>]
uv run traq-admin job set-status --job <job_id_or_job_number> --status NOT_STARTED|DRAFT|SUBMITTED_FOR_PROCESSING|REVIEW_RETURNED|ARCHIVED|FAILED [--host <admin_base_url>] [--api-key <admin_key>]
uv run traq-admin job set-status --job <job_id_or_job_number> --status REVIEW_RETURNED --round-id <round_id> --round-status REVIEW_RETURNED [--host <admin_base_url>] [--api-key <admin_key>]
uv run traq-admin job inspect --job <job_id_or_job_number>
```

Round commands:

```bash
uv run traq-admin round reopen --job-id <job_id> --round-id <round_id> [--host <admin_base_url>] [--api-key <admin_key>]
uv run traq-admin round inspect --job <job_id_or_job_number> --round-id <round_id>
```

Review commands:

```bash
uv run traq-admin review inspect --job <job_id_or_job_number> --round-id <round_id>
```

Final commands:

```bash
uv run traq-admin final inspect --job <job_id_or_job_number>
uv run traq-admin final set-final --job <job_id_or_job_number> --from-json <final_json_path> [--geojson-json <geojson_path>]
uv run traq-admin final set-correction --job <job_id_or_job_number> --from-json <correction_json_path> [--geojson-json <geojson_path>]
```

Network command:

```bash
uv run traq-admin net ipv4 [--json]
uv run traq-admin net ipv6 [--json]
```

### Admin CLI Usage Examples

Interactive mode (recommended):

```bash
export TRAQ_DATABASE_URL='postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo'
uv run traq-admin
```

Inside interactive mode:

```text
show
set host http://127.0.0.1:8000
set api-key demo-key
/net ipv4
/net ipv6
/device pending
/device validate --index 1 --role arborist
/device list --status approved --json
/device issue-token <device_id> --ttl 900
/customer create --name "Sacramento State Arboretum" --phone "555-1212" --address "6000 J St"
/customer list --search Arboretum
/customer usage C0001
/customer merge C0002 --into C0001
/customer billing usage B0001
/customer billing merge B0002 --into B0001
/job create --job-id job_1 --job-number J0001 --customer-id C0001 --billing-profile-id B0001 --tree-number 1 --job-name "Valley Oak"
/job list-assignments
/job assign --job J0001 --device-id <device_id>
/job unassign --job J0001
/job set-status --job J0001 --status DRAFT
/job inspect --job J0001
/job set-status --job J0001 --status REVIEW_RETURNED --round-id round_1 --round-status REVIEW_RETURNED
/round reopen --job-id job_1 --round-id round_1
/round inspect --job J0001 --round-id round_1
/review inspect --job J0001 --round-id round_1
/final inspect --job J0001
exit
```

One-shot mode:

```bash
export TRAQ_DATABASE_URL='postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo'

# Device
uv run traq-admin device pending
uv run traq-admin device validate --index 1 --role arborist
uv run traq-admin device list --status approved --json
uv run traq-admin device approve <device_id> --role arborist
uv run traq-admin device revoke <device_id>
uv run traq-admin device issue-token <device_id> --ttl 900

# Customers
uv run traq-admin customer create --name "Sacramento State Arboretum" --phone "555-1212" --address "6000 J St"
uv run traq-admin customer list --search Arboretum
uv run traq-admin customer update C0001 --phone "555-3434"
uv run traq-admin customer usage C0001
uv run traq-admin customer merge C0002 --into C0001
uv run traq-admin customer billing create --billing-name "City of Trees" --billing-contact-name "A. Manager" --billing-address "123 Elm" --contact-preference email
uv run traq-admin customer billing list --search Trees
uv run traq-admin customer billing update B0001 --contact-preference phone
uv run traq-admin customer billing usage B0001
uv run traq-admin customer billing merge B0002 --into B0001

# Jobs
uv run traq-admin job create --job-id job_1 --job-number J0001 --customer-id C0001 --billing-profile-id B0001 --tree-number 1 --job-name "Valley Oak"
uv run traq-admin job update --job J0001 --customer-id C0001 --billing-profile-id B0001 --tree-number 2 --job-name "Valley Oak Revisit" --status REVIEW_RETURNED
uv run traq-admin job list-assignments --host http://127.0.0.1:8000 --api-key demo-key
uv run traq-admin job assign --job J0001 --device-id <device_id> --host http://127.0.0.1:8000 --api-key demo-key
uv run traq-admin job unassign --job J0001 --host http://127.0.0.1:8000 --api-key demo-key
uv run traq-admin job set-status --job J0001 --status DRAFT --host http://127.0.0.1:8000 --api-key demo-key
uv run traq-admin job inspect --job J0001

# Rounds
uv run traq-admin round reopen --job-id job_1 --round-id round_1 --host http://127.0.0.1:8000 --api-key demo-key
uv run traq-admin round inspect --job J0001 --round-id round_1

# Review / final inspection
uv run traq-admin review inspect --job J0001 --round-id round_1
uv run traq-admin final inspect --job J0001
uv run traq-admin final set-final --job J0001 --from-json ./final.json --geojson-json ./final.geojson
uv run traq-admin final set-correction --job J0001 --from-json ./final_correction.json --geojson-json ./final_correction.geojson

# Network
uv run traq-admin net ipv4
uv run traq-admin net ipv6
```

### Step-by-step: Correct billing or contact information

Use this flow when imported data has duplicate customers, duplicate billing
profiles, or a job is linked to the wrong reusable identity.

Customer and billing records now have short operator-facing codes:
- customers: `C0001`, `C0002`, ...
- billing profiles: `B0001`, `B0002`, ...

Use those codes in the CLI instead of UUIDs whenever possible.

1. Start the CLI:

```bash
uv run traq-admin
```

2. Find likely duplicate records:

```text
/customer duplicates
/customer billing duplicates
/customer list --search Arboretum
/customer billing list --search Sacramento
```

3. Inspect usage before changing anything:

```text
/customer usage C0001
/customer billing usage B0001
```

This shows which jobs will move if you merge the record.

4. If the record is correct and only the text is wrong, update it in place:

```text
/customer update C0001 --name "Sacramento State Arboretum" --phone "555-3434" --address "6000 J St"
/customer billing update B0001 --billing-name "Sacramento State Arboretum" --billing-contact-name "Facilities Office" --billing-address "6000 J St" --contact-preference email
```

5. If two records should be one reusable identity, merge them:

```text
/customer merge C0002 --into C0001
/customer billing merge B0002 --into B0001
```

Merge behavior:
- customer merge reassigns linked jobs to the target customer
- customer merge reconciles customer-scoped tree identities
- billing merge reassigns linked jobs to the target billing profile
- the source record is deleted after reassignment

6. If only one job is wrong, update the job instead of merging identities:

```text
/job update --job J0004 --customer-id C0001 --billing-profile-id B0001
```

7. Verify the result:

```text
/job inspect --job J0004
/customer usage C0001
/customer billing usage B0001
```

Recommended discipline:
- use `usage` before every merge
- use `update` when the record is right but the text is wrong
- use `merge` when two records represent the same real customer or billing identity
- use `job update` when only one job is linked incorrectly
- use `delete` only when `usage` shows no linked jobs

### CLI Verification Against Real PostgreSQL-backed Data

Use imported real jobs and inspect them through the CLI before changing the UI
contract.

Example sequence:

```bash
export TRAQ_DATABASE_URL='postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo'

uv run traq-admin device list --status pending
uv run traq-admin job inspect --job J0004
uv run traq-admin round inspect --job J0004 --round-id round_2
uv run traq-admin review inspect --job J0004 --round-id round_2
uv run traq-admin final inspect --job J0004
```

This verifies the current operational model:

- PostgreSQL-backed runtime state
- local artifact storage for uploaded media and generated outputs
- exported JSON files available for debugging/inspection only

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
