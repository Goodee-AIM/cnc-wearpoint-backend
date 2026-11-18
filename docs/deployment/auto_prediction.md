# CNC WearPoint automatic prediction (no login)

## API contract

`POST /api/measurements/auto-predict` sends multipart `image` and `sensor_csv`.
The Backend reuses the existing upload validator and Object Storage + RDS INSERT,
then runs the established Serving inference and persists prediction/alerts. No
`X-Prediction-Token`, login or session is required by this endpoint. The browser
must never receive the Backend's private `PREDICTION_API_TOKEN`.

Example frontend request:

```javascript
const form = new FormData();
form.append('image', imageFile);
form.append('sensor_csv', sensorCsvFile);
const response = await fetch('/api/measurements/auto-predict', {
  method: 'POST',
  body: form,
});
const payload = await response.json();
if (!response.ok) throw new Error(JSON.stringify(payload.detail));
const { measurement_id, prediction } = payload;
// prediction.predicted_wear_um, predicted_type, status, model_version
```

Success: HTTP 201, `{ "measurement_id": 920, "measurement_status": "completed", "prediction": { ... } }`.
`prediction.status` is wear severity (normal/warning/danger).
If Serving fails after upload, the error includes `detail.measurement_id`;
that measurement can be inspected, but the private retry endpoint still requires
a server token or operator session. This endpoint does not implement a public retry.

## Deployment prerequisites

- Default OFF. Add `AUTO_PREDICTION_ENABLED=0` and
  `AUTO_PREDICTION_ORIGIN=https://aimw.duckdns.org` to Backend environment.
- Keep existing `PREDICTION_API_ENABLED` and private token Backend-only.
- Before setting `AUTO_PREDICTION_ENABLED=1`, apply IP-based rate limiting at
  Nginx/edge, `client_max_body_size` close to 30 MB, request and read timeouts
  suited for the measured inference duration, and logging/monitoring.
- Origin + Host checks block cross-site browser POSTs; **they are not
  authentication**, because non-browser clients can forge those headers.
- The in-process semaphore permits one simultaneous request per Backend
  process; multiple workers/replicas need shared rate limiting.
- No operational change is made by applying this source patch. Ship a newly
  built image only after tests and approval. Then verify an approved test
  upload against RDS/Object Storage and the displayed frontend result.

## Anonymous retry for one failed upload (incremental PR2 patch)

`POST /api/measurements/{measurement_id}/retry` has no multipart body, no login,
and no browser-visible `X-Prediction-Token`. On a 502 after a **committed**
`auto-predict` upload, the Backend returns `detail.measurement_id` and sets a
short-lived `Secure; HttpOnly; SameSite=Strict; Path=/` cookie named
`__Host-cnc_wp_retry_{measurement_id}`. The cookie is signed using a
domain-separated HMAC key derived from the Backend's already-configured private
`PREDICTION_API_TOKEN` (never returned to JavaScript). It expires after 1 hour;
changing the private token invalidates all pending retry capabilities.

A browser on the configured HTTPS origin calls the retry URL with
`credentials: "same-origin"`; the browser attaches the cookie automatically.
The server verifies that the cookie authorizes only this measurement, then
calls the existing `execute_prediction(measurement_id)` without new uploads.
The existing DB claim checks allow only `failed`/`ready` and reject duplicate
predictions, active attempts, and already completed ones. A successful retry
clears that measurement's cookie. A repeated 502 preserves it until expiry.
A `409` indicates an active/completed row and must not be reset automatically.

**Response contract for frontend modal:**

| Case | HTTP | Body / action |
|---|---|---|
| New upload + inference success | 201 | `{measurement_id, measurement_status: "completed", prediction}` |
| Uploaded, inference failed | 502 | `detail: {code: "INFERENCE_FAILED", message, measurement_id}`, show **재추론** button |
| Retry success | 200 | Same prediction body; close modal and display result |
| Retry inference failed | 502 | Same `detail`; keep **재추론** button |
| Busy | 429 | `detail.code: "PREDICTION_BUSY"`, `Retry-After: 30`; show **잠시 후 다시 시도** (do not assume upload exists) |
| Wrong upload / expired cookie / different browser | 403 | Show **재업로드 안내**; no secret in browser code |
| Already predicting or completed | 409 | Do not start another prediction; check measurement status |
| Invalid file | 413/422 | File correction popup; do not offer saved-file retry |
| Disabled / missing configuration | 503 | Temporary service unavailable popup |

**Important:** The 502 path offers retry, but the original `execute_prediction`
may have failed to mark the row `failed` if its database connection failed.
In that case the retry endpoint rejects the row with 409. Inspect state and
follow the manual stale-claim recovery process; never force-reset `predicting`.

**Operational controls:** A valid cookie authorizes *only retry* of one already
uploaded measurement; anonymous fresh uploads still require HTTPS origin and
Nginx/edge IP request limits, body-size limits, and monitoring. Origin and IP
limits cannot completely stop malicious non-browser clients. Multiple Backend
replicas require shared concurrency control; the current semaphore is per
process. Do not expose the public auto endpoint without these controls.

Do not put the private API token in React, Vite variables, HTTP request headers
or error messages. Never ask the browser to read the HttpOnly retry cookie.
