# Technical Note: CLI Command Registry Refactor

## Purpose

This branch exists to reduce maintenance risk in `traq-admin` by replacing the
current manual command wiring with a registry-driven model.

## Current Problem

`admin_cli.py` currently duplicates command knowledge in three places:

- HTTP default injection logic
- handler map construction
- parser registration

That means every new command group or subcommand has to be updated in multiple
places. The file is already large enough that this is a real maintenance risk.

## Intent

The refactor will create one source of truth for CLI command groups and their
registration metadata.

The registry should define:

- command group name
- register function
- handler bindings
- whether cloud mode should inject `--host` and `--api-key`

## Non-Goals

This refactor is not meant to:

- change command syntax
- change REPL command names
- change local/cloud behavior
- redesign backend contracts

## Expected Result

After the refactor:

- `build_parser()` should iterate command group definitions
- HTTP default injection should consult registry metadata
- handler assembly should come from the same registry source
- `admin_cli.py` should become thinner and less error-prone

## Follow-On Value

A command registry lowers the cost of future CLI growth, including project
metadata commands, staging expansion, and additional export/reporting flows.
