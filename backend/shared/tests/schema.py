from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def _executor() -> MigrationExecutor:
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    return executor


def migrate_to(targets):
    executor = _executor()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def app_tip(app_label: str) -> list:
    return list(_executor().loader.graph.leaf_nodes(app_label))


def unapplied_migrations() -> list[str]:
    executor = _executor()
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _ in plan]


def restore_every_migration() -> None:
    executor = _executor()
    executor.migrate(executor.loader.graph.leaf_nodes())

    left = unapplied_migrations()
    if left:
        raise AssertionError(
            "The schema was not restored, which is a defect in this test's rollback and not in whatever else "
            "may have failed alongside it: a rollback took these migrations with it and nothing put them back: "
            + ", ".join(left)
        )
