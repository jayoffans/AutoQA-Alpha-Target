import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import app
from scripts.verify import CASES, VALID_USER, public_addresses, validate_response


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def spec(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("name,method,path,expected,options", CASES, ids=[case[0] for case in CASES])
def test_endpoint_contract(client, spec, name, method, path, expected, options):
    response = client.request(method, path, **options)
    assert response.status_code == expected
    validate_response(spec, method, path, response)
    if path == "/search" and expected == 200:
        assert response.json() == {"q": options["params"]["q"], "limit": options["params"].get("limit", 10), "results": []}
    if path == "/users" and expected == 201:
        assert response.json() == {"id": 2, **options["json"]}
    if name == "protected_absent":
        assert response.headers["www-authenticate"] == "Bearer"
    repeated = client.request(method, path, **options)
    assert repeated.status_code == response.status_code
    assert repeated.json() == response.json()


def test_exact_data_and_no_persistence(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/users/1").json() == {"id": 1, "name": "Alpha User"}
    assert client.post("/users", json=VALID_USER).json() == {"id": 2, **VALID_USER}
    assert client.get("/users/2").status_code == 404
    assert client.get("/protected", headers={"Authorization": "Bearer alpha-demo-token"}).json() == {"status": "authorized"}
    assert client.get("/controlled-error?mode=ok").json() == {"status": "ok", "mode": "ok"}
    assert client.get("/controlled-error?mode=error").json() == {
        "error": "controlled_failure", "message": "Intentional Alpha test failure"
    }


def test_openapi_parameters_schemas_statuses_security(spec):
    expected_statuses = {
        ("/health", "get"): {"200"},
        ("/users/{user_id}", "get"): {"200", "404", "422"},
        ("/users", "post"): {"201", "422"},
        ("/search", "get"): {"200", "422"},
        ("/protected", "get"): {"200", "401", "403"},
        ("/controlled-error", "get"): {"200", "422", "503"},
    }
    for (path, method), statuses in expected_statuses.items():
        assert set(spec["paths"][path][method]["responses"]) == statuses
    path_parameter = spec["paths"]["/users/{user_id}"]["get"]["parameters"][0]
    assert path_parameter["in"] == "path" and path_parameter["required"]
    assert path_parameter["schema"]["minimum"] == 1
    search_params = {item["name"]: item for item in spec["paths"]["/search"]["get"]["parameters"]}
    assert search_params["q"]["in"] == "query" and search_params["q"]["required"]
    assert search_params["q"]["schema"]["minLength"] == 1
    assert search_params["q"]["schema"]["maxLength"] == 120
    assert search_params["limit"]["schema"]["minimum"] == 1
    assert search_params["limit"]["schema"]["maximum"] == 50
    assert spec["paths"]["/controlled-error"]["get"]["parameters"][0]["schema"]["enum"] == ["ok", "error"]
    protected = spec["paths"]["/protected"]["get"]
    assert protected["security"] == [{"AlphaDemoBearer": []}]
    assert spec["components"]["securitySchemes"]["AlphaDemoBearer"]["scheme"] == "bearer"
    body = spec["paths"]["/users"]["post"]["requestBody"]
    assert body["required"]
    schema = spec["components"]["schemas"]["UserCreate"]
    assert set(schema["required"]) == {"name", "email", "age"}
    assert schema["additionalProperties"] is False
    validator = Draft202012Validator(schema)
    validator.validate(VALID_USER)
    for invalid in ({**VALID_USER, "age": 121}, {**VALID_USER, "email": "bad"}, {**VALID_USER, "name": "A"}, {**VALID_USER, "admin": True}):
        assert list(validator.iter_errors(invalid))


@pytest.mark.parametrize("url", ["http://example.com", "https://localhost", "https://127.0.0.1", "https://10.0.0.1", "https://172.16.0.1", "https://192.168.0.1", "https://169.254.169.254", "https://[::1]"])
def test_public_verifier_rejects_private_urls(url):
    with pytest.raises(ValueError):
        public_addresses(url)
