from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0004_v2_challenge_schema"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="authenticationchallengedelivery",
            name="auth_del_proof_state",
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        accepted_at__isnull=True,
                        proof_digest__isnull=True,
                        proof_expires_at__isnull=True,
                        proof_key_id__isnull=True,
                        sending_at__isnull=True,
                        status__in=[
                            "reserved",
                            "suppressed",
                            "abandoned",
                            "superseded",
                            "expired",
                            "invalidated",
                        ],
                    ),
                    models.Q(
                        accepted_at__isnull=True,
                        proof_digest__isnull=False,
                        proof_expires_at__isnull=True,
                        proof_key_id__isnull=False,
                        sending_at__isnull=False,
                        status__in=[
                            "sending",
                            "ambiguous",
                            "rejected",
                            "abandoned",
                            "superseded",
                            "expired",
                            "invalidated",
                        ],
                    )
                    & ~models.Q(proof_key_id=""),
                    models.Q(
                        accepted_at__isnull=False,
                        proof_digest__isnull=False,
                        proof_expires_at__isnull=False,
                        proof_key_id__isnull=False,
                        sending_at__isnull=False,
                        status__in=[
                            "active",
                            "superseded",
                            "consumed",
                            "exhausted",
                            "expired",
                            "invalidated",
                        ],
                    )
                    & ~models.Q(proof_key_id=""),
                    _connector=models.Q.OR,
                ),
                name="auth_del_proof_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="authenticationchallengedelivery",
            constraint=models.CheckConstraint(
                condition=~models.Q(
                    status="superseded",
                    accepted_at__isnull=True,
                )
                | models.Q(purpose="email_change"),
                name="auth_del_supersede_purpose",
            ),
        ),
    ]
