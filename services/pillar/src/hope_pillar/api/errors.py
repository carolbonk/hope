"""`application/problem+json` responses with a machine-readable `code`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from hope_core.auth import ProblemException

PROBLEM_JSON = "application/problem+json"


def problem_response(exc: ProblemException) -> JSONResponse:
    return JSONResponse(exc.body(), status_code=exc.status_code, media_type=PROBLEM_JSON)


async def _problem(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProblemException)
    return problem_response(exc)


async def _validation(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {
            "field": ".".join(str(p) for p in err["loc"] if p != "body") or "body",
            "code": str(err["type"]),
            "message": str(err["msg"]),
        }
        for err in exc.errors()
    ]
    problem = ProblemException(422, "validation_failed", "Check the highlighted fields", errors)
    return problem_response(problem)


def install(app: FastAPI) -> None:
    app.add_exception_handler(ProblemException, _problem)
    app.add_exception_handler(RequestValidationError, _validation)
