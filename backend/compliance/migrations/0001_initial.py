import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AlertProcedureStep",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.PositiveIntegerField(help_text="Order of this step in the procedure (1-based)")),
                ("description", models.CharField(help_text="Brief description of the action to take", max_length=255)),
                (
                    "detailed_instructions",
                    models.TextField(blank=True, help_text="Detailed instructions for completing this step"),
                ),
                ("is_required", models.BooleanField(default=True, help_text="Whether this step must be completed")),
                (
                    "condition",
                    models.CharField(
                        blank=True,
                        help_text="Condition under which this step applies (e.g., 'If SMR required')",
                        max_length=255,
                    ),
                ),
                ("help_text", models.TextField(blank=True, help_text="Additional guidance for completing this step")),
                (
                    "policy_reference",
                    models.CharField(blank=True, help_text="Specific policy reference for this step", max_length=100),
                ),
            ],
            options={
                "verbose_name": "Procedure Step",
                "verbose_name_plural": "⚙️ Setup: Procedure Steps",
                "ordering": ["template", "order"],
            },
        ),
        migrations.CreateModel(
            name="AlertProcedureTemplate",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "alert_type",
                    models.CharField(
                        choices=[
                            ("large_transaction", "Large Transaction (≥AUD 10,000)"),
                            ("rapid_transactions", "Rapid Transactions (5+ in 1 hour)"),
                            ("structuring", "Structuring Pattern"),
                            ("high_aggregate_volume", "High Aggregate Volume (≥AUD 50,000/30 days)"),
                            ("dormant_reactivation", "Dormant Account Reactivation (90+ days)"),
                            ("pattern_deviation", "Material Pattern Deviation (3x average)"),
                            ("round_amounts", "Round Amount Transactions"),
                            ("new_customer_sof", "New Customer SOF Required"),
                            ("extreme_risk_transaction", "Extreme Risk Customer Transaction"),
                            ("high_risk_wallet", "High-Risk Wallet Address"),
                            ("sanctioned_address", "Sanctioned Address"),
                            ("mixer_tumbler", "Mixer/Tumbler Involvement"),
                            ("darknet_association", "Darknet Association"),
                            ("ransomware_association", "Ransomware Association"),
                            ("adverse_media_serious", "Adverse Media (Serious)"),
                            ("adverse_media_minor", "Adverse Media (Minor)"),
                            ("pep_limit_breach", "PEP Hard Limit Breach"),
                            ("info_discrepancy", "Customer Information Discrepancy"),
                            ("failed_documentation", "Failed Documentation Request"),
                            ("multiple_alerts", "Multiple Alerts (3+) Same Customer"),
                            ("sanctions_match", "Sanctions Match"),
                            ("law_enforcement", "Law Enforcement Inquiry"),
                            ("terrorism_financing", "Terrorism Financing Indicators"),
                            ("sanctions_list_update", "New Sanctions List Publication"),
                            ("periodic_review", "Periodic Review Due"),
                            ("manual", "Manual Alert"),
                        ],
                        help_text="The alert type this template applies to",
                        max_length=50,
                        unique=True,
                    ),
                ),
                ("name", models.CharField(help_text="Human-readable name for the procedure", max_length=100)),
                ("description", models.TextField(help_text="Description of when this procedure applies")),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("critical", "Critical (Immediate)"),
                            ("high", "High (1 business day)"),
                            ("medium", "Medium (3 business days)"),
                            ("low", "Low (Per schedule)"),
                        ],
                        default="medium",
                        help_text="Priority level determining response timeframe",
                        max_length=20,
                    ),
                ),
                ("response_time_hours", models.PositiveIntegerField(help_text="Maximum response time in hours")),
                (
                    "policy_references",
                    models.JSONField(
                        default=list, help_text="List of policy document references (e.g., ['Doc 3 §7', 'Doc 5 §12'])"
                    ),
                ),
                (
                    "smr_requirement",
                    models.CharField(
                        choices=[
                            ("mandatory", "Mandatory"),
                            ("likely", "Likely"),
                            ("assess", "Assess based on investigation"),
                            ("unlikely", "Unlikely"),
                        ],
                        default="assess",
                        help_text="Whether SMR is required for this alert type",
                        max_length=20,
                    ),
                ),
                (
                    "smr_timeframe_hours",
                    models.PositiveIntegerField(
                        blank=True, help_text="SMR deadline in hours (24 for TF, 72 for ML)", null=True
                    ),
                ),
                (
                    "escalation_required",
                    models.BooleanField(default=False, help_text="Whether escalation to Director is required"),
                ),
                (
                    "escalation_timeframe",
                    models.CharField(
                        choices=[
                            ("immediate", "Immediate"),
                            ("1_hour", "Within 1 hour"),
                            ("same_day", "Same business day"),
                            ("1_business_day", "Within 1 business day"),
                            ("before_action", "Before action taken"),
                            ("if_concerns", "Only if concerns arise"),
                        ],
                        default="if_concerns",
                        help_text="When escalation should occur",
                        max_length=30,
                    ),
                ),
                (
                    "customer_notification_allowed",
                    models.BooleanField(
                        default=True, help_text="Whether customer can be notified (false for tipping-off risk)"
                    ),
                ),
                (
                    "required_documentation",
                    models.JSONField(
                        default=list, help_text="List of required documentation items for this alert type"
                    ),
                ),
                (
                    "outcome_options",
                    models.JSONField(default=list, help_text="List of possible outcomes with their actions"),
                ),
                ("is_active", models.BooleanField(default=True, help_text="Whether this template is currently in use")),
            ],
            options={
                "verbose_name": "Procedure Template",
                "verbose_name_plural": "⚙️ Setup: Procedure Templates",
                "ordering": ["priority", "alert_type"],
            },
        ),
        migrations.CreateModel(
            name="CustomerRiskAssessment",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assessment_status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("complete", "Complete"), ("incomplete", "Incomplete")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "overall_risk_rating",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("low", "Low Risk"),
                            ("medium", "Medium Risk"),
                            ("high", "High Risk"),
                            ("extreme", "Extreme Risk"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                (
                    "customer_risk_score",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ],
                    ),
                ),
                (
                    "geographic_risk_score",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ],
                    ),
                ),
                (
                    "product_risk_score",
                    models.PositiveSmallIntegerField(
                        default=1,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ],
                    ),
                ),
                (
                    "pep_type",
                    models.CharField(
                        choices=[
                            ("none", "Not a PEP"),
                            ("domestic", "Domestic PEP"),
                            ("foreign", "Foreign PEP"),
                            ("international_org", "International Organisation PEP"),
                            ("family", "PEP Family Member"),
                            ("associate", "PEP Associate"),
                        ],
                        default="none",
                        max_length=20,
                    ),
                ),
                ("pep_details", models.JSONField(blank=True, null=True)),
                ("high_risk_country", models.BooleanField(default=False)),
                ("high_risk_occupation", models.BooleanField(default=False)),
                ("assessment_reason", models.TextField(blank=True)),
                ("is_automated", models.BooleanField(default=True)),
                ("valid_from", models.DateTimeField(blank=True, null=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("next_review_date", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MonitoringRule",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "rule_code",
                    models.CharField(help_text="Unique rule code, e.g., MON-001", max_length=20, unique=True),
                ),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField()),
                (
                    "rule_type",
                    models.CharField(
                        choices=[
                            ("threshold", "Large Transaction Threshold"),
                            ("rapid_transactions", "Rapid Transactions"),
                            ("pattern", "Structuring Pattern"),
                            ("address", "Address Check"),
                            ("sof_required", "New Customer SOF Required"),
                            ("aggregate_volume", "High Aggregate Volume"),
                            ("dormant_reactivation", "Dormant Account Reactivation"),
                            ("pattern_deviation", "Material Pattern Deviation"),
                            ("round_amounts", "Round Amount Transactions"),
                            ("extreme_risk", "Extreme Risk Customer"),
                        ],
                        help_text="Type of check: threshold, velocity, pattern, address, etc.",
                        max_length=30,
                    ),
                ),
                (
                    "parameters",
                    models.JSONField(default=dict, help_text="Rule-specific parameters (thresholds, timeframes, etc.)"),
                ),
                (
                    "alert_severity",
                    models.CharField(
                        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
                        default="medium",
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Monitoring Rule",
                "verbose_name_plural": "⚙️ Setup: Monitoring Rules",
                "ordering": ["rule_code"],
            },
        ),
        migrations.CreateModel(
            name="TransactionScreening",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "sumsub_transaction_id",
                    models.CharField(db_index=True, help_text="Transaction ID used with Sumsub API", max_length=100),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("completed", "Completed"), ("failed", "Failed")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "result",
                    models.CharField(
                        blank=True,
                        choices=[("approved", "Approved"), ("review", "Requires Review"), ("rejected", "Rejected")],
                        help_text="Final screening result: approved, review, or rejected",
                        max_length=20,
                        null=True,
                    ),
                ),
                (
                    "risk_score",
                    models.FloatField(blank=True, help_text="Risk score from 0 (low) to 1.0+ (high)", null=True),
                ),
                (
                    "risk_level",
                    models.CharField(
                        blank=True, help_text="Risk level: LOW, MEDIUM, or HIGH", max_length=20, null=True
                    ),
                ),
                (
                    "risk_signals",
                    models.JSONField(
                        default=list, help_text="List of risk signals detected (sanctions, mixer, darknet, etc.)"
                    ),
                ),
                (
                    "to_address",
                    models.CharField(help_text="Destination wallet address that was screened", max_length=100),
                ),
                (
                    "from_address",
                    models.CharField(
                        blank=True, help_text="Source wallet address (if applicable)", max_length=100, null=True
                    ),
                ),
                (
                    "raw_response",
                    models.JSONField(default=dict, help_text="Complete response from Sumsub API for audit purposes"),
                ),
                (
                    "submitted_at",
                    models.DateTimeField(auto_now_add=True, help_text="When the screening was submitted to Sumsub"),
                ),
                (
                    "completed_at",
                    models.DateTimeField(blank=True, help_text="When the screening result was received", null=True),
                ),
                (
                    "error_message",
                    models.TextField(blank=True, help_text="Error message if screening failed", null=True),
                ),
                ("retry_count", models.PositiveIntegerField(default=0, help_text="Number of retry attempts")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AlertChecklistItem",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_completed", models.BooleanField(default=False, help_text="Whether this step has been completed")),
                ("completed_at", models.DateTimeField(blank=True, help_text="When this step was completed", null=True)),
                ("notes", models.TextField(blank=True, help_text="Notes or findings from completing this step")),
                (
                    "is_skipped",
                    models.BooleanField(default=False, help_text="Whether this step was intentionally skipped"),
                ),
                (
                    "skip_reason",
                    models.CharField(
                        blank=True, help_text="Reason for skipping this step (if skipped)", max_length=255
                    ),
                ),
                (
                    "evidence_references",
                    models.JSONField(
                        blank=True, default=list, help_text="References to evidence or documents related to this step"
                    ),
                ),
                (
                    "completed_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who completed this step",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="completed_checklist_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "step",
                    models.ForeignKey(
                        help_text="The procedure step this tracks",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checklist_items",
                        to="compliance.alertprocedurestep",
                    ),
                ),
            ],
            options={
                "verbose_name": "Checklist Item",
                "verbose_name_plural": "Checklist Items",
                "ordering": ["alert", "step__order"],
            },
        ),
        migrations.AddField(
            model_name="alertprocedurestep",
            name="template",
            field=models.ForeignKey(
                help_text="The procedure template this step belongs to",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="steps",
                to="compliance.alertproceduretemplate",
            ),
        ),
        migrations.CreateModel(
            name="ComplianceAlert",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "alert_type",
                    models.CharField(
                        choices=[
                            ("large_transaction", "Large Transaction (≥AUD 10,000)"),
                            ("rapid_transactions", "Rapid Transactions (5+ in 1 hour)"),
                            ("structuring", "Structuring Pattern"),
                            ("high_aggregate_volume", "High Aggregate Volume (≥AUD 50,000/30 days)"),
                            ("dormant_reactivation", "Dormant Account Reactivation (90+ days)"),
                            ("pattern_deviation", "Material Pattern Deviation (3x average)"),
                            ("round_amounts", "Round Amount Transactions"),
                            ("new_customer_sof", "New Customer SOF Required"),
                            ("extreme_risk_transaction", "Extreme Risk Customer Transaction"),
                            ("high_risk_wallet", "High-Risk Wallet Address"),
                            ("sanctioned_address", "Sanctioned Address"),
                            ("mixer_tumbler", "Mixer/Tumbler Involvement"),
                            ("darknet_association", "Darknet Association"),
                            ("ransomware_association", "Ransomware Association"),
                            ("adverse_media_serious", "Adverse Media (Serious)"),
                            ("adverse_media_minor", "Adverse Media (Minor)"),
                            ("pep_limit_breach", "PEP Hard Limit Breach"),
                            ("info_discrepancy", "Customer Information Discrepancy"),
                            ("failed_documentation", "Failed Documentation Request"),
                            ("multiple_alerts", "Multiple Alerts (3+) Same Customer"),
                            ("sanctions_match", "Sanctions Match"),
                            ("law_enforcement", "Law Enforcement Inquiry"),
                            ("terrorism_financing", "Terrorism Financing Indicators"),
                            ("sanctions_list_update", "New Sanctions List Publication"),
                            ("periodic_review", "Periodic Review Due"),
                            ("manual", "Manual Alert"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
                        max_length=20,
                    ),
                ),
                ("triggered_rule", models.CharField(help_text="Rule code that triggered this alert", max_length=20)),
                ("description", models.TextField()),
                (
                    "alert_data",
                    models.JSONField(
                        default=dict, help_text="Additional data about the alert (thresholds, values, etc.)"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("reviewing", "Under Review"),
                            ("escalated", "Escalated"),
                            ("closed", "Closed"),
                        ],
                        default="new",
                        max_length=20,
                    ),
                ),
                ("assigned_at", models.DateTimeField(blank=True, null=True)),
                ("resolution_notes", models.TextField(blank=True, help_text="Notes on how the alert was resolved")),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "investigation_outcome",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("false_positive", "False Positive"),
                            ("legitimate_activity", "Legitimate Activity"),
                            ("enhanced_monitoring", "Enhanced Monitoring Required"),
                            ("smr_filed", "SMR Filed"),
                            ("account_suspended", "Account Suspended"),
                            ("account_terminated", "Account Terminated"),
                        ],
                        help_text="Final outcome of the investigation",
                        max_length=30,
                        null=True,
                    ),
                ),
                ("smr_required", models.BooleanField(default=False, help_text="Whether an SMR needs to be filed")),
                (
                    "smr_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("tf", "Terrorism Financing (24hr deadline)"),
                            ("ml", "Money Laundering (3 business days)"),
                        ],
                        help_text="Type of SMR: TF (24hr deadline) or ML (3 business days)",
                        max_length=20,
                        null=True,
                    ),
                ),
                (
                    "smr_reference",
                    models.CharField(
                        blank=True,
                        help_text="AUSTRAC SMR reference number (for quick lookup)",
                        max_length=50,
                        null=True,
                    ),
                ),
                (
                    "smr_filed_at",
                    models.DateTimeField(blank=True, help_text="When the SMR was filed with AUSTRAC", null=True),
                ),
                (
                    "account_action",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("none", "No Action"),
                            ("enhanced_monitoring", "Enhanced Monitoring"),
                            ("transaction_hold", "Transaction Hold"),
                            ("suspended", "Account Suspended"),
                            ("terminated", "Account Terminated"),
                        ],
                        help_text="Action taken on the customer account",
                        max_length=30,
                        null=True,
                    ),
                ),
                (
                    "account_action_at",
                    models.DateTimeField(blank=True, help_text="When the account action was applied", null=True),
                ),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_alerts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
