# Tree Identification Frontend Contract

This note describes the exact backend contract for the standalone tree
identification feature.

Endpoint

- `POST /v1/trees/identify`

Auth

- send the normal server auth header:
  - `x-api-key: <token-or-key>`

Request

- frontend UI should use labeled organ slots, not a generic repeated image list
- recommended slots:
  - `leaf`
  - `flower`
  - `fruit`
  - `bark`
- each slot may contain zero or one image
- the frontend should then serialize the filled slots to the multipart request
  contract below

Transport request

- multipart form data
- field `images`:
  - required
  - repeat once for each populated slot
  - current backend accepts up to 5 images total
- field `organs`:
  - repeat once for each populated slot
  - each `organs[n]` must match `images[n]`
  - allowed values:
    - `auto`
    - `bark`
    - `flower`
    - `fruit`
    - `leaf`
- optional form fields:
  - `project`
  - `include_related_images`
  - `no_reject`
  - `nb_results`
  - `lang`

Recommended frontend serialization rule

- build the request from the labeled slots in a stable order:
  - `leaf`
  - `flower`
  - `fruit`
  - `bark`
- for each populated slot:
  - append the image file to `images`
  - append the slot label to `organs`

Example:

- user selects:
  - `leaf`: `leaf.jpg`
  - `bark`: `bark.jpg`
- multipart payload should be:
  - `images`: `leaf.jpg`
  - `organs`: `leaf`
  - `images`: `bark.jpg`
  - `organs`: `bark`

Top-level response contract

The server normalizes the upstream response to exactly these top-level keys:

```json
{
  "query": {},
  "predictedOrgans": [],
  "bestMatch": "",
  "results": [],
  "otherResults": [],
  "version": "",
  "remainingIdentificationRequests": 0
}
```

Exact field guarantees

- `query`
  - type: object
  - guaranteed to be present
  - if upstream `query` is not an object, backend returns `{}`

- `predictedOrgans`
  - type: array
  - guaranteed to be present
  - if upstream `predictedOrgans` is not an array, backend returns `[]`

- `bestMatch`
  - type: string
  - guaranteed to be present
  - backend coerces missing/null values to `""`

- `results`
  - type: array
  - guaranteed to be present
  - if upstream `results` is not an array, backend returns `[]`

- `otherResults`
  - type: array
  - guaranteed to be present
  - if upstream `otherResults` is not an array, backend returns `[]`

- `version`
  - type: string
  - guaranteed to be present
  - backend coerces missing/null values to `""`

- `remainingIdentificationRequests`
  - type: integer
  - guaranteed to be present
  - backend coerces missing/null values to `0`

Important nested-shape rule

The backend guarantees the top-level shape above.

The backend does not currently re-model the nested contents of:

- `query`
- `predictedOrgans[]`
- `results[]`
- `otherResults[]`

Those nested values are passed through from the upstream Pl@ntNet response after
the server confirms only that the top-level container types are correct.

That means the frontend contract is:

- top-level keys and top-level types are stable
- nested fields inside `predictedOrgans[]`, `results[]`, and `otherResults[]`
  must be handled defensively

Current normalization code

The current backend normalization is equivalent to:

- `query = payload["query"] if object else {}`
- `predictedOrgans = payload["predictedOrgans"] if array else []`
- `bestMatch = string(payload["bestMatch"] or "")`
- `results = payload["results"] if array else []`
- `otherResults = payload["otherResults"] if array else []`
- `version = string(payload["version"] or "")`
- `remainingIdentificationRequests = int(payload["remainingIdentificationRequests"] or 0)`

Example successful response

```json
{
  "query": {
    "project": "all"
  },
  "predictedOrgans": [
    {
      "organ": "bark",
      "score": 0.91
    }
  ],
  "bestMatch": "Quercus agrifolia",
  "results": [
    {
      "score": 0.97,
      "species": {
        "scientificNameWithoutAuthor": "Quercus agrifolia",
        "scientificNameAuthorship": "Nee",
        "commonNames": [
          "coast live oak"
        ],
        "family": {
          "scientificNameWithoutAuthor": "Fagaceae"
        },
        "genus": {
          "scientificNameWithoutAuthor": "Quercus"
        }
      }
    }
  ],
  "otherResults": [],
  "version": "2025-01-17 (7.3)",
  "remainingIdentificationRequests": 498
}
```

Error contract

- `400`
  - request validation problem
  - examples:
    - more than 5 images
    - unsupported image content type
    - invalid organs
    - organs count mismatch

- `401` / `403`
  - auth failure according to normal server auth rules

- `502`
  - upstream Pl@ntNet/config/network failure
  - response detail is a backend-generated string

Frontend implementation guidance

- the UI should present separate labeled image pickers for:
  - `leaf`
  - `flower`
  - `fruit`
  - `bark`
- create typed models for the top-level contract above
- treat nested `results[]` and `predictedOrgans[]` structures as upstream data
  that may need defensive parsing
- do not build UI against raw non-normalized upstream responses
