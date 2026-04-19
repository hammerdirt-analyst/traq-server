API Reference
=============

Start with one extractor as the template for docstring style and structure.

Phase 1 round reconciliation adds a dedicated read surface:

- ``GET /v1/jobs/{job_id}/rounds/{round_id}``

Use that route when documenting timeout/retry recovery behavior. It is the
authoritative read for round-level reconciliation state, while
``GET /v1/jobs/{job_id}/rounds/{round_id}/review`` remains the heavier review
payload surface.

.. toctree::
   :maxdepth: 2

   main
   extractors_advanced_assessment_needed
   extractors_common
   extractors_registry
   pdf_fill
   report_letter
   build_traq_full_map
