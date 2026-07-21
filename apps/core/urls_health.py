"""Health and readiness endpoints."""
from django.http import JsonResponse
from django.urls import path


def health(request):
    """Liveness check — process is alive."""
    return JsonResponse({"status": "ok"})


def ready(request):
    """Readiness check — database and migrations OK."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        migrations_ok = len(plan) == 0
    except Exception:
        migrations_ok = False

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    status = "ready" if db_ok and migrations_ok else "not_ready"
    return JsonResponse(
        {
            "status": status,
            "database": "ok" if db_ok else "error",
            "migrations": "ok" if migrations_ok else "pending",
        },
        status=200 if status == "ready" else 503,
    )


urlpatterns = [
    path("", health, name="health"),
    path("ready/", ready, name="ready"),
]
