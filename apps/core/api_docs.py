"""Public, read-only documentation for the partner API."""

import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .rate_limit import rate_limit

_CONTRACT_PATH = Path(settings.BASE_DIR) / "docs" / "openapi.json"
_DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https:; "
    "font-src https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
)


@lru_cache(maxsize=1)
def _load_contract() -> dict:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _secure_docs_response(response: HttpResponse) -> HttpResponse:
    response["Content-Security-Policy"] = _DOCS_CSP
    response["Referrer-Policy"] = "no-referrer"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
@rate_limit(max_requests=120)
def openapi_schema(request):
    """Return the versioned OpenAPI contract without exposing credentials."""
    response = JsonResponse(_load_contract())
    response["Cache-Control"] = "public, max-age=300"
    return _secure_docs_response(response)


@require_GET
@rate_limit(max_requests=120)
def swagger_docs(request):
    """Interactive Swagger UI; protected operations still require an API key."""
    return _secure_docs_response(
        render(request, "api_docs/swagger.html", {"schema_url": "/api/schema/"})
    )


@require_GET
@rate_limit(max_requests=120)
def redoc_docs(request):
    """Read-only ReDoc presentation of the same canonical contract."""
    return _secure_docs_response(
        render(request, "api_docs/redoc.html", {"schema_url": "/api/schema/"})
    )
