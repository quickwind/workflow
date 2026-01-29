from __future__ import annotations

from .settings import *  # noqa: F403


# Tests should be self-contained and not require external services.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
