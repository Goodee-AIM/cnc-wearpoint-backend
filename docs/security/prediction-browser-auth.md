# Browser prediction authentication (Backend only)

This feature has **no React UI**: the current frontend does not call the
operator login or `/predict`. The frontend Set test screen instead uses the
login-free `POST /api/measurements/auto-predict` with upload-scoped HttpOnly
retry/replay cookies (see `docs/deployment/auto_prediction.md`). The operator
session remains available for an operator browser calling
`POST /api/measurements/{measurement_id}/predict` without the private
`X-Prediction-Token` header. Code: `app/core/prediction_session.py`,
`app/api/routers/predictions.py`, `app/services/prediction_execution.py`.

## Deployment prerequisites

- `PREDICTION_API_ENABLED` defaults to `0`; while it is `0`, login, session,
  logout, `/predict` (and also `auto-predict`) return 503. Enable it only after
  the Backend image has passed local and integration tests, schema
  verification, and an approved deployment.
- Require HTTPS at the public Nginx ingress. The Backend cookie has
  `HttpOnly`, `Secure`, `SameSite=Strict`, and the `__Host-` name prefix.
- Set `PREDICTION_BROWSER_ORIGIN=https://aimw.duckdns.org` to the actual public
  HTTPS origin. The browser must use the same host. No trailing slash.
- Set `PREDICTION_OPERATOR_USERNAME` to a nonempty operator login.
- In the Backend environment **only**, set
  `PREDICTION_OPERATOR_PASSWORD_HASH` from:

  ```powershell
  python scripts/hash_prediction_password.py
  ```

  The password prompt does not echo the password. Do not paste the password,
  the generated hash, or any secret into Git/issue comments.
- Generate `PREDICTION_SESSION_SECRET` separately with:

  ```powershell
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

- Keep `PREDICTION_API_TOKEN` only on Backend/authorized internal services;
  never embed it in Vite variables, React bundles, or HTML. The old server API
  can still send `X-Prediction-Token`; a browser never needs it.
- Rate-limit `POST /api/prediction-auth/login` at Nginx or the edge, and
  limit request bodies. There is **no built-in distributed login rate limit**.
- Use the same public HTTPS origin for the Frontend and Backend; this
  avoids cross-origin cookie configuration. Do not broaden CORS to `*`.
- Authenticate upload, GET measurement details and Object Storage links as
  appropriate before exposing this to untrusted users: this patch protects
  *prediction operations*, not every pre-existing API or data resource.

## Operator browser API contract (not used by the current frontend)

All requests below use same-origin HTTPS with `credentials: "include"`.
Login, logout and an authenticated `/predict` require the `Origin` and `Host`
headers to match `PREDICTION_BROWSER_ORIGIN`.

1. `POST /api/prediction-auth/login` JSON:
   `{"username":"operator","password":"<operator password>"}`.
   Successful response: `{ "authenticated": true, "expires_in_seconds": 900 }`.
   The browser receives a secure **HttpOnly cookie**, not the internal token.
2. `GET /api/prediction-auth/session` returns `{ "authenticated": true|false }`.
3. `POST /api/measurements` multipart upload with `image` and `sensor_csv`.
   Returns `measurement_id` (status `ready`). The upload is validated against
   the Serving input rules (PNG/JPEG decoded with Pillow, 600x400 or at least
   1750x1070; 6-column CSV with strictly increasing, constant-interval
   timestamps and at least 512 rows) and rejected with 413/422 otherwise.
4. `POST /api/measurements/{measurement_id}/predict` **without**
   `X-Prediction-Token`, with the operator cookie. The Backend claims the row
   (`predicting`), reads existing Object Storage objects and invokes Serving
   (180 s timeout), then stores the prediction (and an `alerts` row for
   warning/danger, Warning 150 µm / Danger 200 µm recomputed by the Backend).
   For a `failed` measurement without a stored prediction, the same URL
   retries without another upload.
5. `GET /api/measurements/{measurement_id}` to read the persisted status.
6. `POST /api/prediction-auth/logout` clears the browser cookie.

## Error handling and retry safety

- `401`: not logged in, session expired, or invalid `X-Prediction-Token`;
  login is required.
- `403`: origin/host mismatch; do not retry automatically.
- `404`: measurement does not exist.
- `409`: already `predicting`/`completed`, or prediction already stored;
  check the record and do not spawn another prediction.
- `422`: the measurement lacks an image or sensor path, or Serving rejected the
  input files (HTTP 400 from Serving), returned as
  `detail: {code: "INPUT_REJECTED", message, measurement_id}`. The measurement
  is marked `failed`; retrying the same files will be rejected again, so offer
  a re-upload instead of a retry.
- `502`: any other Serving/prediction failure (error, connection failure,
  timeout); Backend attempts to mark the **same** measurement as `failed`.
  Display the retry UI only after confirming that the measurement was
  successfully created and is in `failed` state.
- `503`: feature disabled or server auth misconfigured; operator action needed.
- Backend container crash can leave `predicting`. **Never** auto-reset it on a
  button click. An operator must verify that workers are not still running
  before using the existing 30-minute-minimum recovery procedure
  (`scripts/recover_stale_prediction.py`).
- Do not claim upload files are preserved until a `measurement_id` was
  returned and/or the DB record and object paths have been verified.

## Security limitations and operational controls

- This is a **single-operator, short-lived stateless session** MVP. Logout
  clears the browser cookie but does not invalidate a stolen cookie held by
  another client until expiry (up to 15 minutes); rotate
  `PREDICTION_SESSION_SECRET` to invalidate all sessions.
- Browser cookies can be observed in browser network tools even when HttpOnly;
  HttpOnly prevents JavaScript reading them. The specific shared service
  secret `PREDICTION_API_TOKEN` is never sent to a browser.
- Use HTTPS, a strict origin match, browser session protection, Nginx login
  rate limits, and security monitoring before public operation.

## Verification before any merge/deploy

```powershell
uv run python -m pytest -q tests/test_prediction_execution.py tests/test_prediction_operator_session.py
uv run python -m pytest -q
```

The security tests are offline. As of 2026-11-20 the full local suite reports
`277 passed, 10 skipped`. A real E2E test against Serving + RDS and
Object Storage is a **separate approved step**; do not enable or deploy it
merely because unit tests pass.
