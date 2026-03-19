# `app/main.py` Decomposition Plan

This is a working execution plan for reducing `app/main.py` from a single
large runtime module into a maintainable composition root plus focused routers
and services.

Delete this file when the work is complete.

## Invariants

- No API contract changes during decomposition.
- No auth behavior changes during decomposition.
- No lifecycle/status rule changes during decomposition unless explicitly
  handled as separate bug fixes.
- Existing routes, payloads, and response shapes remain stable.
- Every step is structural first, behavioral only when intentionally scoped.

## Target Shape

Keep `app/main.py` as the thin composition root.

Move endpoint groups into routers:
- `app/api/auth.py`
- `app/api/profile.py`
- `app/api/jobs.py`
- `app/api/rounds.py`
- `app/api/media.py`
- `app/api/finals.py`
- `app/api/admin.py`
- `app/api/lookups.py`

Move request/response models into dedicated modules:
- `app/api/models/auth.py`
- `app/api/models/jobs.py`
- `app/api/models/rounds.py`
- `app/api/models/media.py`
- `app/api/models/finals.py`

## Execution Order

### Phase 1: Extract Models And Services

- extract Pydantic request/response models from `app/main.py`
- extract helper/service clusters while keeping routes in `app/main.py`
- first service/helper targets:
  - assignment/access enforcement
  - review payload assembly/hydration
  - finalization orchestration
  - media/image helper logic
  - job/round persistence helpers

Current progress:
- completed: `app/api/models.py`
- completed: `app/services/access_control_service.py`
- completed: `app/services/review_payload_service.py`
- completed: `app/services/finalization_service.py`
- completed: `app/services/media_runtime_service.py`
- completed: `app/services/runtime_state_service.py`
- completed: `app/services/round_submit_service.py`
- completed: `app/services/review_form_service.py`
- completed: `app/services/device_profile_service.py`
- completed: `app/services/assigned_job_service.py`

### Phase 2: Introduce Shared Runtime Context

- define a small runtime/dependency boundary for:
  - `settings`
  - `db_store`
  - `artifact_store`
  - logger
  - any shared auth/runtime services
- reduce large closure-based helper coupling in `app/main.py`

Current progress:
- completed: `app/runtime_context.py`

### Phase 3: Move Low-Risk Routers First

- move these route groups into routers first:
  - auth
  - profile
  - lookups
  - admin
- register routers from `app/main.py`
- keep behavior unchanged

Current progress:
- completed: `app/api/core_routes.py`
- completed: `app/api/extraction_routes.py`
- completed: `app/api/admin_routes.py`
- completed: `app/api/job_read_routes.py`
- completed: `app/api/job_write_routes.py`
- completed: `app/api/round_manifest_routes.py`
- completed: `app/api/round_submit_routes.py`
- completed: `app/api/round_reprocess_routes.py`
- completed: `app/api/recording_routes.py`
- completed: `app/api/image_routes.py`
- completed: `app/api/final_routes.py`

### Phase 4: Move Core Runtime Routers

- move these route groups after helper extraction is stable:
  - jobs
  - rounds
  - media
  - finals
- keep existing endpoint paths and payloads unchanged

### Phase 5: Reduce `app/main.py` To Composition Root

- app creation
- startup/shutdown wiring
- dependency construction
- router registration only

## Regression Discipline

Run the high-value regression suite after each phase:
- `tests.test_tree_identity_api`
- `tests.test_admin_cli`
- `tests.test_db_store`
- `tests.test_artifact_storage`
- `tests.test_config`

If one phase proves too large, break it again before moving on.

## First Concrete Step

Start with Phase 1 only:
- extract models
- extract helper/service modules
- do not move routes yet

## Notes

- The point is not symmetry for its own sake.
- The point is to shrink risk concentration in `app/main.py`.
- Large router moves should happen only after logic has already been pulled out
  into smaller tested units.
