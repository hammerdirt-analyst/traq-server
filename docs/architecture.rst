Server Architecture Notes
=========================

Managed Extraction Context by Recording Granularity
---------------------------------------------------

The server's extraction accuracy strategy is to keep context narrow by
processing recordings at section-level granularity.

How context is established:

- The user records under a selected section label in the client, and/or
- The user states section context in audio.

Each uploaded recording is tied to its section context and processed in that
scope, rather than feeding one large mixed transcript through extraction.

Tradeoff:

- Backend load and API traffic are higher (typically one upload call per
  recording, plus manifest/submit processing calls).
- In return, extraction precision is significantly higher and user time-on-task
  is lower due to reduced post-processing corrections.

Operational impact:

- More artifacts to track (`recording_id`, per-section transcript cache).
- Better deterministic merges into section-specific form structures.
- Cleaner review loops when users iterate with additional targeted recordings.

