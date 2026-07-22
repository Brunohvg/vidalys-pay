"""Custom exception handler for DRF."""
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    # Handle AuthenticationFailed with standardized format
    if isinstance(exc, AuthenticationFailed):
        code = getattr(exc, "code", "seller_not_authenticated") or "seller_not_authenticated"
        message = _extract_message(exc.detail)
        data = {
            "error": {
                "code": code,
                "message": message,
            }
        }
        response.data = data
        return response

    # Handle Throttled
    if isinstance(exc, Throttled):
        data = {
            "error": {
                "code": "throttled",
                "message": "Muitas requisições. Aguarde e tente novamente.",
            }
        }
        response.data = data
        return response

    # Generic handler
    data = {
        "error": {
            "code": "validation_error" if response.status_code == 400 else "error",
            "message": _extract_message(response.data),
        }
    }
    if hasattr(context.get("request"), "request_id"):
        data["error"]["request_id"] = context["request"].request_id
    response.data = data
    return response


def _extract_message(data):
    """Extract a clean string message from DRF response data.

    Handles ErrorDetail, dict with 'detail' key, list, and plain strings.
    """
    if isinstance(data, str):
        return data

    if hasattr(data, "string"):
        # ErrorDetail — extract the string value
        return str(data.string) if data.string else str(data)

    if isinstance(data, dict):
        # Try common DRF keys
        detail = data.get("detail")
        if detail is not None:
            return _extract_message(detail)
        # Try 'message' key
        message = data.get("message")
        if message is not None:
            return _extract_message(message)
        # Fallback: str representation
        return str(data)

    if isinstance(data, list) and data:
        return _extract_message(data[0])

    return str(data)
