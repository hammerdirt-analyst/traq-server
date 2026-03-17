Tree Identity Contract
======================

Purpose
-------

This note defines the new client/server contract for customer-scoped tree
identity.

Operational rule
----------------

A job has two identifiers:
- ``job_number`` identifies the job
- ``tree_number`` identifies the tree for that customer

Multiple job numbers may refer to the same tree number.

Authoritative source
--------------------

The server is authoritative for ``tree_number``.

Rules:
- for server-created or assigned jobs, the tree number may already be set
- for phone-started jobs, the server resolves or allocates the tree number on
  the first accepted submit
- no GPS-based or fuzzy matching is used

Resolution rule
---------------

For a given customer:
- if a valid ``tree_number`` is supplied, reuse or create that tree identity
- otherwise allocate the next available tree number

Database model
--------------

- ``customers``
- ``trees``
- ``jobs``

Key constraints:
- ``trees`` are unique by ``(customer_id, tree_number)``
- ``jobs`` reference ``tree_id`` and also store ``tree_number`` for operational
  convenience

Client contract impact
----------------------

The client should treat ``tree_number`` as server-authoritative.

This means:
- the client may begin without a final tree number for a phone-started job
- after submit/review return, the client must accept and display the server
  value
- later jobs for the same tree may have different ``job_number`` values but the
  same ``tree_number``

Runtime API contract
--------------------

The live server now exposes tree identity through the operational job endpoints.

``POST /v1/jobs``
    Request accepts:

    - ``customer_name`` (optional but strongly preferred)
    - ``tree_number`` (optional provisional customer-scoped tree number)

    Response returns:

    - authoritative ``job_number``
    - authoritative ``tree_number``

``GET /v1/jobs/assigned``
    Each assigned job row includes ``tree_number``.

``GET /v1/jobs/{job_id}``
    Status payload includes ``tree_number``.

``POST /v1/jobs/{job_id}/rounds/{round_id}/submit``
    The server reads any provisional ``client_tree_details.tree_number`` in the
    submitted form, resolves the authoritative tree identity, writes that value
    back into the working form payload, and returns top-level ``tree_number`` in
    the submit response.

``GET /v1/jobs/{job_id}/rounds/{round_id}/review``
    Review payload includes top-level ``tree_number`` and the canonical
    ``client_tree_details.tree_number`` inside the returned form payload.

``POST /v1/jobs/{job_id}/rounds/{round_id}/reprocess``
    Reprocess response includes top-level ``tree_number``.

``POST /v1/jobs/{job_id}/final``
    Final submission resolves the authoritative tree identity one last time from
    the submitted form payload, writes it back into the finalized form, and then
    generates final artifacts.

Implementation status
---------------------

Current status:
- schema support added
- tree allocation helper added
- importer seeds tree identities from legacy final form data where available
- runtime job/create/status/review/submit/final paths now return or enforce the
  authoritative tree number
