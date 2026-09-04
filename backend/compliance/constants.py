from decimal import Decimal

# THRESHOLDS & TIME PERIODS

ALERT_THRESHOLD_AUD = Decimal("10000")
SCREENING_THRESHOLD_AUD = Decimal("5000")

RISK_THRESHOLD_LOW = 4
RISK_THRESHOLD_MEDIUM = 6
RISK_THRESHOLD_HIGH = 8

NEW_CUSTOMER_DAYS = 30
RISK_REVIEW_PERIOD_MONTHS = 24
BATCH_MONITORING_LOOKBACK_HOURS = 2
# Only transactions mined within this window are screened on creation; older ones
# arrive through historical wallet syncs and are handled by the batch task.
TRANSACTION_MONITORING_WINDOW_HOURS = 1

DOMESTIC_PEP_RISK_ADJUSTMENT = 2

AGGREGATE_VOLUME_THRESHOLD_AUD = Decimal("50000")
AGGREGATE_VOLUME_PERIOD_DAYS = 30
DORMANT_ACCOUNT_DAYS = 90
PATTERN_DEVIATION_MULTIPLIER = 3
PATTERN_DEVIATION_BASELINE_DAYS = 90
PATTERN_DEVIATION_MIN_HISTORY = 5
ROUND_AMOUNT_DIVISOR = Decimal("5000")
ROUND_AMOUNT_COUNT_THRESHOLD = 3
ROUND_AMOUNT_PERIOD_DAYS = 30

# CUSTOMER RISK ASSESSMENT

ASSESSMENT_STATUS_PENDING = "pending"
ASSESSMENT_STATUS_COMPLETE = "complete"
ASSESSMENT_STATUS_INCOMPLETE = "incomplete"

ASSESSMENT_STATUS_CHOICES = [
    (ASSESSMENT_STATUS_PENDING, "Pending"),
    (ASSESSMENT_STATUS_COMPLETE, "Complete"),
    (ASSESSMENT_STATUS_INCOMPLETE, "Incomplete"),
]

RISK_RATING_LOW = "low"
RISK_RATING_MEDIUM = "medium"
RISK_RATING_HIGH = "high"
RISK_RATING_EXTREME = "extreme"

RISK_RATING_CHOICES = [
    (RISK_RATING_LOW, "Low Risk"),
    (RISK_RATING_MEDIUM, "Medium Risk"),
    (RISK_RATING_HIGH, "High Risk"),
    (RISK_RATING_EXTREME, "Extreme Risk"),
]

HIGH_RISK_RATINGS = [RISK_RATING_HIGH, RISK_RATING_EXTREME]

# MONITORING RULES

RULE_TYPE_THRESHOLD = "threshold"
RULE_TYPE_RAPID_TRANSACTIONS = "rapid_transactions"
RULE_TYPE_PATTERN = "pattern"
RULE_TYPE_ADDRESS = "address"
RULE_TYPE_SOF_REQUIRED = "sof_required"
RULE_TYPE_AGGREGATE_VOLUME = "aggregate_volume"
RULE_TYPE_DORMANT_REACTIVATION = "dormant_reactivation"
RULE_TYPE_PATTERN_DEVIATION = "pattern_deviation"
RULE_TYPE_ROUND_AMOUNTS = "round_amounts"
RULE_TYPE_EXTREME_RISK = "extreme_risk"

RULE_TYPE_CHOICES = [
    (RULE_TYPE_THRESHOLD, "Large Transaction Threshold"),
    (RULE_TYPE_RAPID_TRANSACTIONS, "Rapid Transactions"),
    (RULE_TYPE_PATTERN, "Structuring Pattern"),
    (RULE_TYPE_ADDRESS, "Address Check"),
    (RULE_TYPE_SOF_REQUIRED, "New Customer SOF Required"),
    (RULE_TYPE_AGGREGATE_VOLUME, "High Aggregate Volume"),
    (RULE_TYPE_DORMANT_REACTIVATION, "Dormant Account Reactivation"),
    (RULE_TYPE_PATTERN_DEVIATION, "Material Pattern Deviation"),
    (RULE_TYPE_ROUND_AMOUNTS, "Round Amount Transactions"),
    (RULE_TYPE_EXTREME_RISK, "Extreme Risk Customer"),
]

# COMPLIANCE ALERTS

# Transaction-based alerts
ALERT_TYPE_LARGE_TRANSACTION = "large_transaction"
ALERT_TYPE_RAPID_TRANSACTIONS = "rapid_transactions"
ALERT_TYPE_STRUCTURING = "structuring"
ALERT_TYPE_HIGH_AGGREGATE_VOLUME = "high_aggregate_volume"
ALERT_TYPE_DORMANT_REACTIVATION = "dormant_reactivation"
ALERT_TYPE_PATTERN_DEVIATION = "pattern_deviation"
ALERT_TYPE_ROUND_AMOUNTS = "round_amounts"
ALERT_TYPE_NEW_CUSTOMER_SOF = "new_customer_sof"
ALERT_TYPE_EXTREME_RISK_TRANSACTION = "extreme_risk_transaction"

# Blockchain/address-based alerts
ALERT_TYPE_HIGH_RISK_WALLET = "high_risk_wallet"
ALERT_TYPE_SANCTIONED_ADDRESS = "sanctioned_address"
ALERT_TYPE_MIXER_TUMBLER = "mixer_tumbler"
ALERT_TYPE_DARKNET_ASSOCIATION = "darknet_association"
ALERT_TYPE_RANSOMWARE_ASSOCIATION = "ransomware_association"

# Customer-based alerts
ALERT_TYPE_ADVERSE_MEDIA_SERIOUS = "adverse_media_serious"
ALERT_TYPE_ADVERSE_MEDIA_MINOR = "adverse_media_minor"
ALERT_TYPE_PEP_LIMIT_BREACH = "pep_limit_breach"
ALERT_TYPE_INFO_DISCREPANCY = "info_discrepancy"
ALERT_TYPE_FAILED_DOCUMENTATION = "failed_documentation"
ALERT_TYPE_MULTIPLE_ALERTS = "multiple_alerts"

# External/regulatory alerts
ALERT_TYPE_SANCTIONS_MATCH = "sanctions_match"
ALERT_TYPE_LAW_ENFORCEMENT = "law_enforcement"
ALERT_TYPE_TERRORISM_FINANCING = "terrorism_financing"
ALERT_TYPE_SANCTIONS_LIST_UPDATE = "sanctions_list_update"

# Review-based alerts
ALERT_TYPE_PERIODIC_REVIEW = "periodic_review"

# Other
ALERT_TYPE_MANUAL = "manual"

ALERT_TYPE_CHOICES = [
    # Transaction-based
    (ALERT_TYPE_LARGE_TRANSACTION, "Large Transaction (≥AUD 10,000)"),
    (ALERT_TYPE_RAPID_TRANSACTIONS, "Rapid Transactions (5+ in 1 hour)"),
    (ALERT_TYPE_STRUCTURING, "Structuring Pattern"),
    (ALERT_TYPE_HIGH_AGGREGATE_VOLUME, "High Aggregate Volume (≥AUD 50,000/30 days)"),
    (ALERT_TYPE_DORMANT_REACTIVATION, "Dormant Account Reactivation (90+ days)"),
    (ALERT_TYPE_PATTERN_DEVIATION, "Material Pattern Deviation (3x average)"),
    (ALERT_TYPE_ROUND_AMOUNTS, "Round Amount Transactions"),
    (ALERT_TYPE_NEW_CUSTOMER_SOF, "New Customer SOF Required"),
    (ALERT_TYPE_EXTREME_RISK_TRANSACTION, "Extreme Risk Customer Transaction"),
    # Blockchain/address-based
    (ALERT_TYPE_HIGH_RISK_WALLET, "High-Risk Wallet Address"),
    (ALERT_TYPE_SANCTIONED_ADDRESS, "Sanctioned Address"),
    (ALERT_TYPE_MIXER_TUMBLER, "Mixer/Tumbler Involvement"),
    (ALERT_TYPE_DARKNET_ASSOCIATION, "Darknet Association"),
    (ALERT_TYPE_RANSOMWARE_ASSOCIATION, "Ransomware Association"),
    # Customer-based
    (ALERT_TYPE_ADVERSE_MEDIA_SERIOUS, "Adverse Media (Serious)"),
    (ALERT_TYPE_ADVERSE_MEDIA_MINOR, "Adverse Media (Minor)"),
    (ALERT_TYPE_PEP_LIMIT_BREACH, "PEP Hard Limit Breach"),
    (ALERT_TYPE_INFO_DISCREPANCY, "Customer Information Discrepancy"),
    (ALERT_TYPE_FAILED_DOCUMENTATION, "Failed Documentation Request"),
    (ALERT_TYPE_MULTIPLE_ALERTS, "Multiple Alerts (3+) Same Customer"),
    # External/regulatory
    (ALERT_TYPE_SANCTIONS_MATCH, "Sanctions Match"),
    (ALERT_TYPE_LAW_ENFORCEMENT, "Law Enforcement Inquiry"),
    (ALERT_TYPE_TERRORISM_FINANCING, "Terrorism Financing Indicators"),
    (ALERT_TYPE_SANCTIONS_LIST_UPDATE, "New Sanctions List Publication"),
    # Review-based
    (ALERT_TYPE_PERIODIC_REVIEW, "Periodic Review Due"),
    # Other
    (ALERT_TYPE_MANUAL, "Manual Alert"),
]

ALERT_SEVERITY_LOW = "low"
ALERT_SEVERITY_MEDIUM = "medium"
ALERT_SEVERITY_HIGH = "high"
ALERT_SEVERITY_CRITICAL = "critical"

ALERT_SEVERITY_CHOICES = [
    (ALERT_SEVERITY_LOW, "Low"),
    (ALERT_SEVERITY_MEDIUM, "Medium"),
    (ALERT_SEVERITY_HIGH, "High"),
    (ALERT_SEVERITY_CRITICAL, "Critical"),
]

ALERT_STATUS_NEW = "new"
ALERT_STATUS_REVIEWING = "reviewing"
ALERT_STATUS_ESCALATED = "escalated"
ALERT_STATUS_CLOSED = "closed"

ALERT_STATUS_CHOICES = [
    (ALERT_STATUS_NEW, "New"),
    (ALERT_STATUS_REVIEWING, "Under Review"),
    (ALERT_STATUS_ESCALATED, "Escalated"),
    (ALERT_STATUS_CLOSED, "Closed"),
]

# TRANSACTION SCREENING

SCREENING_STATUS_PENDING = "pending"
SCREENING_STATUS_COMPLETED = "completed"
SCREENING_STATUS_FAILED = "failed"

SCREENING_STATUS_CHOICES = [
    (SCREENING_STATUS_PENDING, "Pending"),
    (SCREENING_STATUS_COMPLETED, "Completed"),
    (SCREENING_STATUS_FAILED, "Failed"),
]

SCREENING_RESULT_APPROVED = "approved"
SCREENING_RESULT_REVIEW = "review"
SCREENING_RESULT_REJECTED = "rejected"

SCREENING_RESULT_CHOICES = [
    (SCREENING_RESULT_APPROVED, "Approved"),
    (SCREENING_RESULT_REVIEW, "Requires Review"),
    (SCREENING_RESULT_REJECTED, "Rejected"),
]

# INVESTIGATIONS & SMR

INVESTIGATION_OUTCOME_FALSE_POSITIVE = "false_positive"
INVESTIGATION_OUTCOME_LEGITIMATE = "legitimate_activity"
INVESTIGATION_OUTCOME_ENHANCED_MONITORING = "enhanced_monitoring"
INVESTIGATION_OUTCOME_SMR_FILED = "smr_filed"
INVESTIGATION_OUTCOME_ACCOUNT_SUSPENDED = "account_suspended"
INVESTIGATION_OUTCOME_ACCOUNT_TERMINATED = "account_terminated"

INVESTIGATION_OUTCOME_CHOICES = [
    (INVESTIGATION_OUTCOME_FALSE_POSITIVE, "False Positive"),
    (INVESTIGATION_OUTCOME_LEGITIMATE, "Legitimate Activity"),
    (INVESTIGATION_OUTCOME_ENHANCED_MONITORING, "Enhanced Monitoring Required"),
    (INVESTIGATION_OUTCOME_SMR_FILED, "SMR Filed"),
    (INVESTIGATION_OUTCOME_ACCOUNT_SUSPENDED, "Account Suspended"),
    (INVESTIGATION_OUTCOME_ACCOUNT_TERMINATED, "Account Terminated"),
]

SMR_TYPE_TF = "tf"
SMR_TYPE_ML = "ml"

SMR_TYPE_CHOICES = [
    (SMR_TYPE_TF, "Terrorism Financing (24hr deadline)"),
    (SMR_TYPE_ML, "Money Laundering (3 business days)"),
]

ACCOUNT_ACTION_NONE = "none"
ACCOUNT_ACTION_ENHANCED_MONITORING = "enhanced_monitoring"
ACCOUNT_ACTION_TRANSACTION_HOLD = "transaction_hold"
ACCOUNT_ACTION_SUSPENDED = "suspended"
ACCOUNT_ACTION_TERMINATED = "terminated"

ACCOUNT_ACTION_CHOICES = [
    (ACCOUNT_ACTION_NONE, "No Action"),
    (ACCOUNT_ACTION_ENHANCED_MONITORING, "Enhanced Monitoring"),
    (ACCOUNT_ACTION_TRANSACTION_HOLD, "Transaction Hold"),
    (ACCOUNT_ACTION_SUSPENDED, "Account Suspended"),
    (ACCOUNT_ACTION_TERMINATED, "Account Terminated"),
]

# PEP (POLITICALLY EXPOSED PERSONS)

PEP_TYPE_NONE = "none"
PEP_TYPE_DOMESTIC = "domestic"
PEP_TYPE_FOREIGN = "foreign"
PEP_TYPE_INTERNATIONAL_ORG = "international_org"
PEP_TYPE_FAMILY = "family"
PEP_TYPE_ASSOCIATE = "associate"

PEP_TYPE_CHOICES = [
    (PEP_TYPE_NONE, "Not a PEP"),
    (PEP_TYPE_DOMESTIC, "Domestic PEP"),
    (PEP_TYPE_FOREIGN, "Foreign PEP"),
    (PEP_TYPE_INTERNATIONAL_ORG, "International Organisation PEP"),
    (PEP_TYPE_FAMILY, "PEP Family Member"),
    (PEP_TYPE_ASSOCIATE, "PEP Associate"),
]

PEP_REJECTION_TYPES = [
    PEP_TYPE_FOREIGN,
    PEP_TYPE_INTERNATIONAL_ORG,
    PEP_TYPE_FAMILY,
    PEP_TYPE_ASSOCIATE,
]

# GEOGRAPHIC RISK (FATF BLACKLIST)

FATF_BLACKLIST_COUNTRIES = ["KP", "IR", "MM"]

# HIGH-RISK OCCUPATIONS

HIGH_RISK_OCCUPATIONS = [
    "politician",
    "government_official",
    "military_senior",
    "judiciary",
    "diplomat",
    "state_enterprise_executive",
    "casino_gaming",
    "money_services",
    "precious_metals",
    "real_estate_agent",
    "lawyer_accountant",
    "arms_dealer",
]

# ALERT PROCEDURE TEMPLATES

PROCEDURE_PRIORITY_CRITICAL = "critical"
PROCEDURE_PRIORITY_HIGH = "high"
PROCEDURE_PRIORITY_MEDIUM = "medium"
PROCEDURE_PRIORITY_LOW = "low"

PROCEDURE_PRIORITY_CHOICES = [
    (PROCEDURE_PRIORITY_CRITICAL, "Critical (Immediate)"),
    (PROCEDURE_PRIORITY_HIGH, "High (1 business day)"),
    (PROCEDURE_PRIORITY_MEDIUM, "Medium (3 business days)"),
    (PROCEDURE_PRIORITY_LOW, "Low (Per schedule)"),
]

SMR_REQUIREMENT_MANDATORY = "mandatory"
SMR_REQUIREMENT_LIKELY = "likely"
SMR_REQUIREMENT_ASSESS = "assess"
SMR_REQUIREMENT_UNLIKELY = "unlikely"

SMR_REQUIREMENT_CHOICES = [
    (SMR_REQUIREMENT_MANDATORY, "Mandatory"),
    (SMR_REQUIREMENT_LIKELY, "Likely"),
    (SMR_REQUIREMENT_ASSESS, "Assess based on investigation"),
    (SMR_REQUIREMENT_UNLIKELY, "Unlikely"),
]

ESCALATION_TIMEFRAME_IMMEDIATE = "immediate"
ESCALATION_TIMEFRAME_1_HOUR = "1_hour"
ESCALATION_TIMEFRAME_SAME_DAY = "same_day"
ESCALATION_TIMEFRAME_1_BUSINESS_DAY = "1_business_day"
ESCALATION_TIMEFRAME_BEFORE_ACTION = "before_action"
ESCALATION_TIMEFRAME_IF_CONCERNS = "if_concerns"

ESCALATION_TIMEFRAME_CHOICES = [
    (ESCALATION_TIMEFRAME_IMMEDIATE, "Immediate"),
    (ESCALATION_TIMEFRAME_1_HOUR, "Within 1 hour"),
    (ESCALATION_TIMEFRAME_SAME_DAY, "Same business day"),
    (ESCALATION_TIMEFRAME_1_BUSINESS_DAY, "Within 1 business day"),
    (ESCALATION_TIMEFRAME_BEFORE_ACTION, "Before action taken"),
    (ESCALATION_TIMEFRAME_IF_CONCERNS, "Only if concerns arise"),
]
