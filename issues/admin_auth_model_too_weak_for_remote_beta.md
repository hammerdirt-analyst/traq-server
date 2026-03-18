# Admin Auth Model Is Too Weak For Remote Beta

## Problem

The current security model is acceptable for local development, but it is too
weak for a remotely reachable beta deployment.

Today, effective admin access is controlled primarily by a single shared server
API key (`TRAQ_API_KEY`). There is no distinct admin user identity, no admin
login flow, no admin session model, and no separation between named operators.

This is workable when the admin is simply the person with local repo access and
shell access. It is not a strong enough model once the server is deployed on
GCP and reachable over the public internet.

## Current Security Model

### Device access

Normal device workflow is:
1. device registers with `POST /v1/auth/register-device`
2. device polls `GET /v1/auth/device/{device_id}/status`
3. once approved, device requests token via `POST /v1/auth/token`
4. device uses that issued token for authenticated job/profile/media requests

This part is directionally correct.

### Admin access

Admin authority currently comes from:
- the shared server master key (`TRAQ_API_KEY`)
- optionally, a device token whose role was approved as `admin`

The main server auth path is `require_api_key()` in `app/main.py`:
- if `X-API-Key` matches `TRAQ_API_KEY`, the caller is treated as admin
- otherwise the same header is treated as a device token and validated from DB

That means the server-wide master key is the primary admin credential.

## Why This Feels Weak

The concern is correct. The current setup is weak for remote beta because:

1. one shared secret controls broad admin power
- compromise of `TRAQ_API_KEY` compromises the admin surface
- there is no operator attribution
- rotation affects all operators/scripts at once

2. there is no named admin identity model
- no per-person login
- no individual revocation
- no audit trail by human admin identity

3. device auth and admin auth share the same request header shape
- operationally convenient
- but conceptually muddy
- increases the chance of bootstrap/auth confusion on the client side

4. admin CLI security is implicit, not explicit
- currently the admin is effectively "whoever can run the CLI with the key"
- that is fine on a trusted local workstation
- it is not a strong remote operating model

## What Is Still Sound

The device-side restrictions are not the main weakness.

For non-admin device usage, the current approach is reasonable for beta:
- devices must register
- devices must be approved
- devices receive issued bearer tokens
- assigned-job endpoints are limited by device token / assignment checks

So the weak point is not "unregistered devices can use all endpoints".
The weak point is the admin/authz model around remote operations.

## Minimum Beta Position

Before remote beta, the server should at least move to this posture:

- keep device token auth for field devices
- keep bootstrap endpoints open only where required for registration flow
- stop relying on a single shared API key as the long-term admin model
- define a distinct admin path for remote operations

## Recommended Direction

There are two realistic paths.

### Option A: keep admin operations off the public app surface

- keep the mobile/device API public
- keep admin CLI usage limited to trusted operator environment
- do not expose broad admin mutation workflows to arbitrary internet clients
- use network/IP restrictions, VPN, or operator-only environment where needed

This is the smallest change.

### Option B: introduce a real admin identity layer

Examples:
- Google identity / IAP protecting admin surface
- OAuth/OIDC-backed admin login
- named admin users with separate credentials and sessions

This is the stronger long-term direction.

## Recommended Immediate Action

For remote beta, do not treat the current shared `TRAQ_API_KEY` model as the
finished security model.

Record the current posture as:
- acceptable for local development
- acceptable for controlled internal beta only if tightly managed
- not sufficient as the final remote admin auth design

## Follow-up Questions

- Which admin actions must be remotely accessible in beta?
- Can admin CLI usage be restricted to a trusted operator machine/environment?
- Do we want Google-backed admin auth rather than building password auth?
- Do we need per-admin attribution before external beta?
