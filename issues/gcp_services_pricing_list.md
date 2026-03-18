# GCP Services Pricing List

## Purpose

Concise list of the GCP services currently proposed for TRAQ server deployment so pricing can be gathered.

## Core Services

### 1. Cloud Run
Purpose:
- run the TRAQ API server container

Cost drivers:
- request count
- CPU allocation
- memory allocation
- instance time
- network egress

### 2. Cloud SQL for PostgreSQL
Purpose:
- managed PostgreSQL for authoritative runtime state

Cost drivers:
- instance size
- storage size
- backups
- high availability option
- network egress

### 3. Cloud Storage
Purpose:
- store uploaded and generated artifacts

Planned artifact classes:
- uploaded audio
- uploaded images
- generated report images
- final PDFs / DOCX
- optional exported GeoJSON files

Cost drivers:
- total storage volume
- object operations
- retrievals
- network egress

## Supporting Services

### 4. Artifact Registry
Purpose:
- store server container images for deployment

Cost drivers:
- stored image size
- image retention count
- network egress

### 5. Secret Manager
Purpose:
- store deployment secrets

Expected secrets:
- database credentials / connection string
- `TRAQ_API_KEY`
- `OPENAI_API_KEY`

Cost drivers:
- number of active secrets
- access operations

## Optional Services

### 6. Cloud Logging / Monitoring
Purpose:
- operational logs, metrics, alerting

Cost drivers:
- log ingestion volume
- retention
- metrics / alerting usage

### 7. Cloud Build
Purpose:
- GCP-native image build pipeline

Cost drivers:
- build minutes
- artifact output volume

## Minimum Stack To Price First

If pricing needs to start with the minimum realistic deployment set, price:

1. Cloud Run
2. Cloud SQL for PostgreSQL
3. Cloud Storage
4. Artifact Registry
5. Secret Manager

## Current Recommendation

Planned target stack:

- Cloud Run
- Cloud SQL for PostgreSQL
- Cloud Storage
- Artifact Registry
- Secret Manager

Optional later:

- Cloud Logging / Monitoring
- Cloud Build
