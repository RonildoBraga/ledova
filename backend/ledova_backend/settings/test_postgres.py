"""PostgreSQL settings for the isolated RLS proof tests."""

from copy import deepcopy

from .database import DATABASES as POSTGRES_DATABASES
from .test import *  # noqa: F401,F403

# The wildcard import intentionally supplies the credential-free test
# settings. Replace only its SQLite database with a copy of the normal
# environment-driven PostgreSQL configuration.
DATABASES = deepcopy(POSTGRES_DATABASES)

# Use a fresh normally migrated test database. The proof test creates and
# removes its temporary role and policies itself; no runtime RLS migration is
# shipped.
try:
    del MIGRATION_MODULES  # noqa: F821
except NameError:
    pass

# Session state must never survive between proof-test connections.
DATABASES["default"]["CONN_MAX_AGE"] = 0
