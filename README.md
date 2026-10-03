# AutoQA-Alpha-Target

Controlled public API target for AutoQA Studio Alpha testing.

This independent FastAPI service contains **only synthetic test data**, **no production
data**, and **no secrets**. Responses are deterministic and the service is safe for
automated QA against its documented routes. It does not store users or perform database
queries, outbound URL requests, command execution, uploads, or application file I/O.
`alpha-demo-token` is a public test constant, not a credential. No AutoQA Studio code
or SSRF policy is part of this repository.

## Run and test

Python 3.11 or later:

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-dev.txt
python -m pytest -q
python -m app.start
```

The server listens on `0.0.0.0`, using `PORT` or local default `8000`.
OpenAPI is at `/openapi.json`; FastAPI's built-in interactive documentation is at `/docs`.
Production dependencies are separately pinned, including transitive packages and hashes,
in `requirements.txt`. Test tools are excluded from the container.

## API contract

| Method | Path | Input | Expected status |
| --- | --- | --- | --- |
| GET | `/health` | none | 200, `{"status":"ok"}` |
| GET | `/users/{user_id}` | integer `1` | 200, fixed Alpha User |
| GET | `/users/{user_id}` | positive integer other than `1` | 404 |
| GET | `/users/{user_id}` | non-integer or integer <= 0 | 422 |
| POST | `/users` | valid JSON `name`, `email`, `age` | 201, fixed ID `2` with echoed fields |
| POST | `/users` | invalid, missing, or extra fields; malformed JSON | 422 |
| GET | `/search` | required `q`, optional `limit` (default 10) | 200, echoed query and empty results |
| GET | `/search` | invalid/missing `q` or invalid `limit` | 422 |
| GET | `/protected` | no Authorization header | 401, `WWW-Authenticate: Bearer` |
| GET | `/protected` | wrong token, malformed header, or wrong scheme | 403 |
| GET | `/protected` | `Authorization: Bearer alpha-demo-token` | 200 |
| GET | `/controlled-error` | omitted mode or `mode=ok` | 200 |
| GET | `/controlled-error` | `mode=error` | 503, structured controlled failure |
| GET | `/controlled-error` | any other mode | 422 |
| GET | `/openapi.json` | none | 200, OpenAPI 3.1 document |

Validation boundaries are inclusive:

- `name`: 2–80 characters, containing at least one non-whitespace character.
- `email`: 6–254 characters with the explicit ASCII regex published in OpenAPI.
  The local part uses `[A-Za-z0-9._%+-]+`; the domain has at least two dotted
  alphanumeric/hyphen labels, each starting and ending with an alphanumeric character.
  This deliberately limited test format makes no DNS queries and is not full RFC email validation.
- `age`: a JSON integer from 0 through 120; strings, booleans, and fractional numbers are rejected.
- `q`: 1–120 characters, containing at least one non-whitespace character.
- `limit`: integer from 1 through 50.

POST never persists data: subsequent `GET /users/2` still returns 404.
Validation errors use FastAPI/Pydantic's standard 422 response. Error response schemas
for 401, 403, 404, 422 and the intentional 503 are documented. Bearer authentication
uses the OpenAPI HTTP bearer security scheme.

Example creation:

```sh
curl -i -H 'Content-Type: application/json' \
  -d '{"name":"Alpha User","email":"alpha@example.com","age":30}' \
  http://localhost:8000/users
```

## Docker

```sh
docker build -t autoqa-alpha-target:local .
docker run -d --name autoqa-alpha-target-local \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -e PORT=8080 -p 127.0.0.1:8080:8080 autoqa-alpha-target:local
python -m scripts.verify http://127.0.0.1:8080 --output artifacts/docker-verification.json
docker stop autoqa-alpha-target-local
docker rm autoqa-alpha-target-local
```

The Linux image runs as UID/GID `10001:10001`. Its exec-form Python entry point reads
`PORT` directly without a shell. There is no volume or writable application storage requirement.

## Railway

Create a new Railway project and one independent service. Do not select or modify
AutoQA Studio, AutoQA Demo, or their databases. `railway.toml` selects the Dockerfile,
one replica, and the `/health` deployment healthcheck. No user-supplied secret or
database configuration is required; the container consumes Railway's `PORT`.

```sh
railway init --name AutoQA-Alpha-Target --workspace YOUR_WORKSPACE_ID --json
railway add --service AutoQA-Alpha-Target --json
railway up --service AutoQA-Alpha-Target --detach
railway domain --service AutoQA-Alpha-Target --json
python -m scripts.verify https://YOUR_DOMAIN.up.railway.app \
  --require-public --output artifacts/public-verification.json
```

The verifier requires trusted HTTPS, rejects redirects, checks every resolved DNS
address is public, exercises all endpoint scenarios and boundary/security inputs,
and validates every API response against the OpenAPI served by that deployment.
It also checks repeated successful inputs and absence of persistence.
Verification reports and local environment files are ignored by Git and Railway uploads.

Official Railway documentation: [CLI deployment](https://docs.railway.com/cli/up),
[public domains](https://docs.railway.com/cli/domain), and
[healthchecks](https://docs.railway.com/deployments/healthchecks).
