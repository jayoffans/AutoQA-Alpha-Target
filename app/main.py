"""Stateless, deterministic endpoints containing only synthetic test data."""

from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field


EMAIL_PATTERN = (
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+$"
)
DEMO_TOKEN = "alpha-demo-token"  # Public test constant; never a secret.


class Health(BaseModel):
    status: Literal["ok"]


class User(BaseModel):
    id: Literal[1]
    name: Literal["Alpha User"]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=80, pattern=r"\S")
    email: str = Field(
        min_length=6,
        max_length=254,
        pattern=EMAIL_PATTERN,
        description="ASCII test email: local part [A-Za-z0-9._%+-]+ and dotted domain labels."
        " Labels must begin and end with an alphanumeric character. No DNS lookup.",
    )
    age: int = Field(ge=0, le=120, strict=True)


class CreatedUser(UserCreate):
    id: Literal[2]


class SearchResult(BaseModel):
    q: str
    limit: int
    results: list[User]


class DetailError(BaseModel):
    detail: str


class ProtectedResult(BaseModel):
    status: Literal["authorized"]


class ControlledOK(BaseModel):
    status: Literal["ok"]
    mode: Literal["ok"]


class ControlledFailure(BaseModel):
    error: Literal["controlled_failure"]
    message: Literal["Intentional Alpha test failure"]


app = FastAPI(
    title="AutoQA-Alpha-Target",
    version="1.0.0",
    description="Controlled public API target for AutoQA Studio Alpha testing. "
    "Synthetic test data only; stateless and deterministic. "
    "The public demo bearer token is alpha-demo-token.",
    redoc_url=None,
)
bearer = HTTPBearer(
    auto_error=False,
    scheme_name="AlphaDemoBearer",
    description="Public test constant: alpha-demo-token. Missing header: 401; "
    "invalid scheme, malformed header, or wrong token: 403. No real authentication.",
)


@app.get("/health", response_model=Health, tags=["health"])
def health() -> Health:
    return Health(status="ok")


@app.get(
    "/users/{user_id}",
    response_model=User,
    responses={404: {"model": DetailError, "description": "Positive ID other than 1."}},
    tags=["users"],
)
def get_user(user_id: Annotated[int, Path(ge=1)]) -> User:
    """Only ID 1 exists. Non-integer or non-positive IDs produce validation 422."""
    if user_id != 1:
        raise HTTPException(status_code=404, detail="User not found")
    return User(id=1, name="Alpha User")


@app.post("/users", status_code=201, response_model=CreatedUser, tags=["users"])
def create_user(body: UserCreate) -> CreatedUser:
    """Echo validated input with fixed ID 2. Nothing is stored; GET /users/2 remains 404."""
    return CreatedUser(id=2, **body.model_dump())


@app.get("/search", response_model=SearchResult, tags=["search"])
def search(
    q: Annotated[str, Query(min_length=1, max_length=120, pattern=r"\S")],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SearchResult:
    """Echo the query with an empty result list. Whitespace-only q is invalid."""
    return SearchResult(q=q, limit=limit, results=[])


@app.get(
    "/protected",
    response_model=ProtectedResult,
    responses={
        401: {
            "model": DetailError,
            "description": "Authorization header absent.",
            "headers": {"WWW-Authenticate": {"schema": {"type": "string"}}},
        },
        403: {"model": DetailError, "description": "Authorization present but invalid."},
    },
    tags=["security"],
)
def protected(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
) -> ProtectedResult:
    """Require the public demo token. The header's presence distinguishes 401 from 403."""
    if "authorization" not in request.headers:
        raise HTTPException(
            status_code=401,
            detail="Authorization required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials is None or credentials.credentials != DEMO_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid demo token")
    return ProtectedResult(status="authorized")


@app.get(
    "/controlled-error",
    response_model=ControlledOK,
    responses={
        503: {"model": ControlledFailure, "description": "Intentional failure for mode=error."},
    },
    tags=["controlled-error"],
)
def controlled_error(
    mode: Annotated[Literal["ok", "error"], Query()] = "ok",
) -> ControlledOK | JSONResponse:
    """Both 200 and 503 are documented test outcomes. Other modes produce 422."""
    if mode == "error":
        failure = ControlledFailure(
            error="controlled_failure", message="Intentional Alpha test failure"
        )
        return JSONResponse(status_code=503, content=failure.model_dump())
    return ControlledOK(status="ok", mode="ok")
