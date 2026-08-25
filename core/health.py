from django.db import connection
from django.http import JsonResponse


def health(request):
    """Liveness/readiness para o balanceador: banco e cache respondem?"""
    ok = {"db": False, "cache": False}
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        ok["db"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        from django.core.cache import cache

        cache.set("health", "1", 5)
        ok["cache"] = cache.get("health") == "1"
    except Exception:  # noqa: BLE001
        pass
    return JsonResponse({"status": "ok" if all(ok.values()) else "degradado", **ok}, status=200 if all(ok.values()) else 503)
