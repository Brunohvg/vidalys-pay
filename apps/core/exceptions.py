"""Custom exception handler for DRF."""
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        data = {
            "error": {
                "code": "validation_error" if response.status_code == 400 else "error",
                "message": str(response.data) if isinstance(response.data, dict) else response.data,
            }
        }
        if hasattr(context.get("request"), "request_id"):
            data["error"]["request_id"] = context["request"].request_id
        response.data = data
    return response
