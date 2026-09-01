"""Test settings that run against PostgreSQL (for RLS-dependent tests).

Inherits the credential-free test settings but swaps SQLite for the real
Postgres service, and KEEPS migrations enabled so the tenancy RLS migration
(and every other) is applied — RLS policies live in migrations, not models.
"""

from .test import *  # noqa: F401,F403
from .database import DATABASES  # noqa: F401  real Postgres config from env

# test.py disables migrations (SQLite, model-first). RLS policies are created
# by migrations, so re-enable them here.
try:
    del MIGRATION_MODULES  # noqa: F821
except NameError:
    pass
