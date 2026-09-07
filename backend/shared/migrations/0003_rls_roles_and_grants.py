from django.conf import settings
from django.db import migrations

CREATE_ROLES = """
DO $$
DECLARE
    app_role   text := %(app)s;
    oper_role  text := %(operator)s;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
        EXECUTE format('CREATE ROLE %%I LOGIN', app_role);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = oper_role) THEN
        EXECUTE format('CREATE ROLE %%I LOGIN', oper_role);
    END IF;

    EXECUTE format('ALTER ROLE %%I NOBYPASSRLS', app_role);
    EXECUTE format('ALTER ROLE %%I BYPASSRLS', oper_role);
    EXECUTE format('ALTER ROLE %%I BYPASSRLS', current_user);

    EXECUTE format('GRANT %%I, %%I TO %%I', app_role, oper_role, current_user);
    EXECUTE format('GRANT CONNECT ON DATABASE %%I TO %%I, %%I', current_database(), app_role, oper_role);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %%I, %%I', app_role, oper_role);
    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %%I, %%I', app_role, oper_role
    );
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %%I, %%I', app_role, oper_role);
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %%I IN SCHEMA public '
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %%I, %%I',
        current_user, app_role, oper_role
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %%I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %%I, %%I',
        current_user, app_role, oper_role
    );
END
$$;
"""

DROP_GRANTS = """
DO $$
DECLARE
    app_role   text := %(app)s;
    oper_role  text := %(operator)s;
BEGIN
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %%I IN SCHEMA public '
        'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM %%I, %%I',
        current_user, app_role, oper_role
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %%I IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM %%I, %%I',
        current_user, app_role, oper_role
    );
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %%I, %%I', app_role, oper_role);
    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %%I, %%I', app_role, oper_role);
    EXECUTE format('REVOKE USAGE ON SCHEMA public FROM %%I, %%I', app_role, oper_role);
    EXECUTE format('REVOKE CONNECT ON DATABASE %%I FROM %%I, %%I', current_database(), app_role, oper_role);
END
$$;
"""


def _run(sql):
    def apply(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        roles = settings.RLS_ROLES
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(sql, {"app": roles["app"], "operator": roles["operator"]})

    return apply


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0002_drop_celery_tables"),
    ]

    operations = [
        migrations.RunPython(_run(CREATE_ROLES), _run(DROP_GRANTS)),
    ]
