"""PostgreSQL settings for the full test suite (the CI PostgreSQL stage)."""

from copy import deepcopy

from .database import DATABASES as POSTGRES_DATABASES
from .test import *  # noqa: F401,F403

# The wildcard import intentionally supplies the credential-free test
# settings. Replace only its SQLite database with a copy of the normal
# environment-driven PostgreSQL configuration.
DATABASES = deepcopy(POSTGRES_DATABASES)

# Run real migrations so the schema under test is the shipped one.
try:
    del MIGRATION_MODULES  # noqa: F821
except NameError:
    pass

# Session state must never survive between test connections.
DATABASES["default"]["CONN_MAX_AGE"] = 0
