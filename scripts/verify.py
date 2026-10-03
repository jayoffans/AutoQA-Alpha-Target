"""Verify HTTP behavior against the served OpenAPI, optionally requiring public HTTPS."""

import argparse
import ipaddress
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from jsonschema import Draft202012Validator


VALID_USER = {"name": "Alpha User", "email": "alpha@example.com", "age": 30}
CASES = [
    ("health", "GET", "/health", 200, {}),
    ("user_exists", "GET", "/users/1", 200, {}),
    ("user_missing", "GET", "/users/999", 404, {}),
    ("user_not_persisted", "GET", "/users/2", 404, {}),
    ("user_bad_type", "GET", "/users/not-an-int", 422, {}),
    ("user_zero", "GET", "/users/0", 422, {}),
    ("user_negative", "GET", "/users/-1", 422, {}),
    ("create_valid", "POST", "/users", 201, {"json": VALID_USER}),
    ("create_age_min", "POST", "/users", 201, {"json": {**VALID_USER, "age": 0}}),
    ("create_age_max", "POST", "/users", 201, {"json": {**VALID_USER, "age": 120}}),
    ("create_name_min", "POST", "/users", 201, {"json": {**VALID_USER, "name": "AB"}}),
    ("create_name_max", "POST", "/users", 201, {"json": {**VALID_USER, "name": "A" * 80}}),
    ("create_name_short", "POST", "/users", 422, {"json": {**VALID_USER, "name": "A"}}),
    ("create_name_long", "POST", "/users", 422, {"json": {**VALID_USER, "name": "A" * 81}}),
    ("create_name_blank", "POST", "/users", 422, {"json": {**VALID_USER, "name": "  "}}),
    ("create_age_low", "POST", "/users", 422, {"json": {**VALID_USER, "age": -1}}),
    ("create_age_high", "POST", "/users", 422, {"json": {**VALID_USER, "age": 121}}),
    ("create_age_string", "POST", "/users", 422, {"json": {**VALID_USER, "age": "30"}}),
    ("create_age_boolean", "POST", "/users", 422, {"json": {**VALID_USER, "age": True}}),
    ("create_age_float", "POST", "/users", 422, {"json": {**VALID_USER, "age": 30.5}}),
    ("create_email_invalid", "POST", "/users", 422, {"json": {**VALID_USER, "email": "bad"}}),
    ("create_email_bad_domain", "POST", "/users", 422, {"json": {**VALID_USER, "email": "a@-example.com"}}),
    ("create_email_long", "POST", "/users", 422, {"json": {**VALID_USER, "email": "a" * 250 + "@example.com"}}),
    ("create_missing", "POST", "/users", 422, {"json": {"name": "Alpha User"}}),
    ("create_extra", "POST", "/users", 422, {"json": {**VALID_USER, "admin": True}}),
    ("create_malformed_json", "POST", "/users", 422, {"content": "{", "headers": {"Content-Type": "application/json"}}),
    ("search_default", "GET", "/search", 200, {"params": {"q": "alpha"}}),
    ("search_min", "GET", "/search", 200, {"params": {"q": "a", "limit": 1}}),
    ("search_max", "GET", "/search", 200, {"params": {"q": "a" * 120, "limit": 50}}),
    ("search_low", "GET", "/search", 422, {"params": {"q": "alpha", "limit": 0}}),
    ("search_high", "GET", "/search", 422, {"params": {"q": "alpha", "limit": 51}}),
    ("search_bad_limit", "GET", "/search", 422, {"params": {"q": "alpha", "limit": "bad"}}),
    ("search_empty", "GET", "/search", 422, {"params": {"q": ""}}),
    ("search_blank", "GET", "/search", 422, {"params": {"q": "  "}}),
    ("search_long", "GET", "/search", 422, {"params": {"q": "a" * 121}}),
    ("search_missing", "GET", "/search", 422, {}),
    ("protected_absent", "GET", "/protected", 401, {}),
    ("protected_wrong", "GET", "/protected", 403, {"headers": {"Authorization": "Bearer wrong"}}),
    ("protected_scheme", "GET", "/protected", 403, {"headers": {"Authorization": "Basic alpha-demo-token"}}),
    ("protected_malformed", "GET", "/protected", 403, {"headers": {"Authorization": "Bearer"}}),
    ("protected_valid", "GET", "/protected", 200, {"headers": {"Authorization": "Bearer alpha-demo-token"}}),
    ("controlled_default", "GET", "/controlled-error", 200, {}),
    ("controlled_ok", "GET", "/controlled-error", 200, {"params": {"mode": "ok"}}),
    ("controlled_error", "GET", "/controlled-error", 503, {"params": {"mode": "error"}}),
    ("controlled_invalid", "GET", "/controlled-error", 422, {"params": {"mode": "invalid"}}),
    ("security_sql_echo", "GET", "/search", 200, {"params": {"q": "' OR 1=1; DROP TABLE users;--"}}),
    ("security_url_echo", "GET", "/search", 200, {"params": {"q": "http://169.254.169.254/latest/meta-data/"}}),
    ("security_shell_echo", "POST", "/users", 201, {"json": {**VALID_USER, "name": "$(whoami); <script>alert(1)</script>"}}),
]


def public_addresses(base_url: str) -> list[str]:
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("A public HTTPS URL without embedded credentials is required")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Use a base URL without a path, query, or fragment")
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443)})
    if not addresses or not all(ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("All DNS addresses must be globally routable")
    return addresses


def validate_response(spec: dict, method: str, path: str, response) -> None:
    template = "/users/{user_id}" if path.startswith("/users/") else path
    operation = spec["paths"][template][method.lower()]
    definition = operation["responses"].get(str(response.status_code))
    assert definition is not None, f"Undocumented status: {method} {path} {response.status_code}"
    schema = definition["content"]["application/json"]["schema"]
    assert response.headers["content-type"].startswith("application/json")
    root_schema = {**schema, "components": spec["components"]}
    Draft202012Validator(root_schema).validate(response.json())


def verify(base_url: str, require_public: bool = False) -> dict:
    addresses = public_addresses(base_url) if require_public else []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30, follow_redirects=False) as client:
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        spec = openapi.json()
        assert spec["info"]["title"] == "AutoQA-Alpha-Target"
        assert spec["components"]["securitySchemes"]["AlphaDemoBearer"] == {
            "type": "http", "description": spec["components"]["securitySchemes"]["AlphaDemoBearer"]["description"], "scheme": "bearer"
        }
        results = [{"name": "openapi", "method": "GET", "path": "/openapi.json", "expected": 200, "actual": 200}]
        for name, method, path, expected, options in CASES:
            response = client.request(method, path, **options)
            assert response.status_code == expected, f"{name}: {response.status_code} != {expected}"
            validate_response(spec, method, path, response)
            if expected in (200, 201):
                repeated = client.request(method, path, **options)
                assert repeated.status_code == expected and repeated.json() == response.json(), name
            if path == "/search" and expected == 200:
                assert response.json() == {"q": options["params"]["q"], "limit": options["params"].get("limit", 10), "results": []}
            if path == "/users" and expected == 201:
                assert response.json() == {"id": 2, **options["json"]}
            if name == "protected_absent":
                assert response.headers["www-authenticate"] == "Bearer"
            results.append({"name": name, "method": method, "path": path, "expected": expected, "actual": response.status_code})
        assert client.get("/users/2").status_code == 404
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/users/1").json() == {"id": 1, "name": "Alpha User"}
        assert client.get("/controlled-error", params={"mode": "error"}).json() == {
            "error": "controlled_failure", "message": "Intentional Alpha test failure"
        }
    return {"base_url": base_url, "dns_addresses": addresses, "passed": len(results), "failed": 0, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--require-public", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.base_url, args.require_public)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
