# CNC WearPoint automatic prediction (no login)

The frontend **Set test** screen uses this API: one PNG/JPEG image and one sensor
CSV are uploaded and inferred in a single request. Code:
`app/api/routers/auto_prediction.py`, `app/api/routers/measurements.py`
(upload validation), `app/services/prediction_execution.py` (Serving call and
persistence), `app/services/manual_replay_prediction.py` (replay).

## API contract

`POST /api/measurements/auto-predict` sends multipart `image` and `sensor_csv`.
The Backend reuses the existing upload validator and Object Storage + RDS INSERT
(`source_type='upload'`), then runs the established Serving inference and
persists the prediction (and an `alerts` row for warning/danger). No
`X-Prediction-Token`, login or session is required by this endpoint. The browser
must never receive the Backend's private `PREDICTION_API_TOKEN`.

Upload validation mirrors the Serving input rules, so files Serving would
reject are normally refused before anything is stored (HTTP 413/422, no
measurement row):

| Item | Rule |
|---|---|
| Image | PNG or JPEG signature, <= 8 MB, fully decoded with Pillow; 600x400 ROI image or a fixed-camera original of at least 1750x1070 (fixed ROI `1150, 670, 1750, 1070`) |
| Sensor CSV | headerless 6 columns (acc, audio, force_x, force_y, force_z, timestamp), finite numbers, UTF-8, <= 20 MB |
| Timestamps | no duplicate or backwards timestamps; constant sampling interval within the file |
| Rows | at least 512 data rows (model window size) |

Example frontend request:

```javascript
const form = new FormData();
form.append('image', imageFile);
form.append('sensor_csv', sensorCsvFile);
const response = await fetch('/api/measurements/auto-predict', {
  method: 'POST',
  body: form,
  credentials: 'same-origin',
});
const payload = await response.json();
if (!response.ok) throw new Error(JSON.stringify(payload.detail));
const { measurement_id, prediction } = payload;
// prediction.predicted_wear_um, predicted_type, status, model_version
```

Success: HTTP 201, `{ "measurement_id": 920, "measurement_status": "completed", "prediction": { ... } }`.
`prediction.status` is wear severity (normal/warning/danger), recomputed by the
Backend with Warning 150 µm / Danger 200 µm instead of Serving's own judgement.
A success also sets an upload-scoped replay cookie (see below).

If Serving fails after the upload is committed, the measurement is marked
`failed` and the error includes `detail.measurement_id`:

- Serving HTTP 400 (input files rejected): HTTP **422**,
  `detail: {code: "INPUT_REJECTED", message, measurement_id}`. No retry cookie is
  issued because the same files would be rejected again.
- Any other Serving error, connection failure or timeout: HTTP **502**,
  `detail: {code: "INFERENCE_FAILED", message, measurement_id}`, plus a one-shot
  retry cookie.

The Backend waits up to 180 s for Serving. The frontend aborts after 200 s.
Production Serving uses model Version 2 (`candidate-opt`, same weights as
Version 1, optimized inference) since 2026-11-20; inference takes about 1.1 s on
average.

## Deployment prerequisites

- Default OFF. Both `AUTO_PREDICTION_ENABLED=1` and `PREDICTION_API_ENABLED=1`
  are required; otherwise every endpoint here returns 503.
- `AUTO_PREDICTION_ORIGIN` must be the exact public HTTPS origin
  (e.g. `https://aimw.duckdns.org`, no path or trailing slash). Requests whose
  `Origin` and `Host` headers do not match return 403.
- `PREDICTION_API_TOKEN` must be at least 32 characters; the cookie signing keys
  are derived from it. Without it the request fails with 503 before any
  Object Storage / RDS write.
- Keep the private token Backend-only.
- Before enabling, apply IP-based rate limiting at Nginx/edge,
  `client_max_body_size` close to 30 MB (the repository Nginx example uses
  40 MB), request and read timeouts longer than the 180 s Serving timeout, and
  logging/monitoring.
- Origin + Host checks block cross-site browser POSTs; **they are not
  authentication**, because non-browser clients can forge those headers.
- Concurrency: manual requests (auto-predict, replay-predict, retry) share one
  in-process slot (`manual_inference_slots` in
  `app/services/inference_capacity.py`). A second concurrent manual request gets
  429 `PREDICTION_BUSY`. The Set4~11 monitoring inference worker uses a separate
  slot, so monitoring inference never makes a manual request fail with 429.
  Slots are per process; multiple workers/replicas need shared rate limiting.
- Ship a newly built image only after tests and approval, then verify an
  approved test upload against RDS/Object Storage and the displayed frontend
  result.

## Anonymous retry for one failed upload

`POST /api/measurements/{measurement_id}/retry` has no multipart body, no login,
and no browser-visible `X-Prediction-Token`. On a 502 after a **committed**
`auto-predict` upload, the Backend returns `detail.measurement_id` and sets a
short-lived `Secure; HttpOnly; SameSite=Strict; Path=/` cookie named
`__Host-cnc_wp_retry_{measurement_id}`. The cookie is signed using a
domain-separated HMAC key derived from the Backend's already-configured private
`PREDICTION_API_TOKEN` (never returned to JavaScript). It expires after 1 hour;
changing the private token invalidates all pending retry and replay capabilities.

A browser on the configured HTTPS origin calls the retry URL with
`credentials: "same-origin"`; the browser attaches the cookie automatically.
The server verifies that the cookie authorizes only this measurement, then
calls the existing `execute_prediction(measurement_id)` without new uploads.
The existing DB claim checks allow only `failed`/`ready` and reject duplicate
predictions, active attempts, and already completed ones. A successful retry
clears that measurement's retry cookie and issues a replay cookie. A repeated
502 preserves the retry cookie until expiry. A `409` indicates an
active/completed row and must not be reset automatically.

## Replay of a successful upload

`POST /api/measurements/{measurement_id}/replay-predict` runs a **fresh** Serving
inference on the same stored image and CSV (Set test "다시 재생"). It requires
the `__Host-cnc_wp_replay_{measurement_id}` cookie, which is issued only after a
successful `auto-predict` or `retry` and renewed after each successful replay
(1 hour). Only `source_type='upload'` rows in `completed` state can be replayed.
Each replay appends a new `predictions` row; the measurement row and earlier
prediction/alert rows are unchanged, and no `alerts` row is written.

**Response contract for frontend modal:**

| Case | HTTP | Body / action |
|---|---|---|
| New upload + inference success | 201 | `{measurement_id, measurement_status: "completed", prediction}` + replay cookie |
| Uploaded, Serving rejected input | 422 | `detail: {code: "INPUT_REJECTED", message, measurement_id}`; show the message, no retry button |
| Uploaded, inference failed | 502 | `detail: {code: "INFERENCE_FAILED", message, measurement_id}`, show **재추론** button |
| Retry success | 200 | Same prediction body; close modal and display result |
| Retry inference failed | 502 | Same `detail`; keep **재추론** button |
| Replay success | 200 | Same prediction body |
| Replay inference failed | 502 | `detail: {code: "REPLAY_FAILED", message, measurement_id}` |
| Busy | 429 | `detail.code: "PREDICTION_BUSY"`, `Retry-After: 30`; show **잠시 후 다시 시도** (do not assume upload exists) |
| Wrong upload / expired cookie / different browser | 403 | Show **재업로드 안내**; no secret in browser code |
| Already predicting or completed (retry) / not completed or changed (replay) | 409 | Do not start another prediction; check measurement status |
| Invalid file | 413/422 | Upload validation message (string `detail`); do not offer saved-file retry |
| Disabled / missing configuration | 503 | Temporary service unavailable popup |

The current frontend shows the server's concrete 422 reason (validation string
or `INPUT_REJECTED` message), shows the **재추론** button only for 502 with a
`measurement_id`, and has separate messages for 504, client timeout and network
errors.

**Important:** The 502 path offers retry, but the original `execute_prediction`
may have failed to mark the row `failed` if its database connection failed.
In that case the retry endpoint rejects the row with 409. Inspect state and
follow the manual stale-claim recovery process
(`scripts/recover_stale_prediction.py`, at least 30 minutes old); never
force-reset `predicting`.

**Operational controls:** A valid cookie authorizes *only retry or replay* of one
already uploaded measurement; anonymous fresh uploads still require HTTPS origin
and Nginx/edge IP request limits, body-size limits, and monitoring. Origin and IP
limits cannot completely stop malicious non-browser clients. Multiple Backend
replicas require shared concurrency control; the current slot is per process.
Do not expose the public auto endpoint without these controls.

Do not put the private API token in React, Vite variables, HTTP request headers
or error messages. Never ask the browser to read the HttpOnly cookies.

Tests: `tests/test_auto_prediction.py`, `tests/test_manual_replay_capability.py`,
`tests/test_manual_replay_prediction.py`, `tests/test_upload_validation.py`,
`tests/test_inference_capacity.py`.
