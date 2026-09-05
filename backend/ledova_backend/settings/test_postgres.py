from copy import deepcopy

from .database import DATABASES as POSTGRES_DATABASES
from .test import *  # noqa: F401,F403

DATABASES = deepcopy(POSTGRES_DATABASES)


try:
    del MIGRATION_MODULES  # noqa: F821
except NameError:
    pass


DATABASES["default"]["CONN_MAX_AGE"] = 0
