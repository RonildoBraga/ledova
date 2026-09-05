from django.db import migrations

CELERY_TABLES = [
    "django_celery_beat_periodictask",
    "django_celery_beat_periodictasks",
    "django_celery_beat_clockedschedule",
    "django_celery_beat_crontabschedule",
    "django_celery_beat_intervalschedule",
    "django_celery_beat_solarschedule",
    "django_celery_results_taskresult",
    "django_celery_results_chordcounter",
    "django_celery_results_groupresult",
]

DROP_SQL = "\n".join(f"DROP TABLE IF EXISTS {name} CASCADE;" for name in CELERY_TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=DROP_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
