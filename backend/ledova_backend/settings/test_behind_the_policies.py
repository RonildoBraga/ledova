from .test_postgres import *  # noqa: F401,F403

RLS_ROLE_PER_REQUEST = True
TEST_RUNNER = "shared.behind_the_policies_runner.BehindThePoliciesRunner"
