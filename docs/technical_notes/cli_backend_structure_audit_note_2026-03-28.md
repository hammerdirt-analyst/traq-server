# CLI Backend Structure Audit

This branch exists to reduce maintenance hotspots in the operator CLI before the
next cross-layer feature is added.

Initial findings:

- `tests/test_admin_cli.py` had become the default landing zone for unrelated
  CLI behavior and was too large to maintain comfortably
- `admin_cli.py` still carries multiple responsibilities: parser wiring,
  command wrappers, REPL behavior, and context/bootstrap logic
- `app/cli/remote_backend.py` and `app/cli/local_backend.py` remain large and
  carry parallel domain logic that will become harder to evolve as features are
  added

Intent for this branch:

- split the CLI tests into focused modules with a shared fixture
- identify the next high-value extraction seam in the CLI/runtime layer
- avoid changing the operator command surface while improving maintainability
- keep testing close to each structural change so refactors stay controlled
