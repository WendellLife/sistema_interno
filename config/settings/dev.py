from .base import *  # noqa: F401,F403

DEBUG = True
INSTALLED_APPS += ["django_extensions", "debug_toolbar"]  # noqa: F405
MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
INTERNAL_IPS = ["127.0.0.1"]
