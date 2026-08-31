from .base import *  # noqa: F401,F403

DEBUG = True
INSTALLED_APPS += ["django_extensions", "debug_toolbar"]  # noqa: F405
MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
INTERNAL_IPS = ["127.0.0.1"]

# O painel de cache do debug-toolbar serializa em JSON tudo o que passa pelo cache, e
# `core.permissions.matriz()` guarda um dict com chave de TUPLA — (papel, módulo). Isso
# levanta TypeError dentro do middleware e devolve 500 na primeira requisição que toca o
# cache, /tarefas/ inclusive. O resto da barra continua ligado.
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": {
        "debug_toolbar.panels.profiling.ProfilingPanel",
        "debug_toolbar.panels.redirects.RedirectsPanel",
        "debug_toolbar.panels.cache.CachePanel",
    }
}
