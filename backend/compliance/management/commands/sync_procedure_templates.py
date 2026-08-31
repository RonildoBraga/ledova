"""
Management command to sync alert procedure templates.

This command ensures all required procedure templates and their steps exist in the database.
It uses update_or_create to be idempotent - safe to run multiple times.

Usage:
    python manage.py sync_procedure_templates
    python manage.py sync_procedure_templates --verbosity 2  # Show details
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from compliance.constants import (
    ALERT_TYPE_ADVERSE_MEDIA_MINOR,
    ALERT_TYPE_ADVERSE_MEDIA_SERIOUS,
    ALERT_TYPE_DARKNET_ASSOCIATION,
    ALERT_TYPE_DORMANT_REACTIVATION,
    ALERT_TYPE_FAILED_DOCUMENTATION,
    ALERT_TYPE_HIGH_AGGREGATE_VOLUME,
    ALERT_TYPE_HIGH_RISK_WALLET,
    ALERT_TYPE_INFO_DISCREPANCY,
    ALERT_TYPE_LARGE_TRANSACTION,
    ALERT_TYPE_LAW_ENFORCEMENT,
    ALERT_TYPE_MIXER_TUMBLER,
    ALERT_TYPE_MULTIPLE_ALERTS,
    ALERT_TYPE_NEW_CUSTOMER_SOF,
    ALERT_TYPE_PATTERN_DEVIATION,
    ALERT_TYPE_PEP_LIMIT_BREACH,
    ALERT_TYPE_PERIODIC_REVIEW,
    ALERT_TYPE_RANSOMWARE_ASSOCIATION,
    ALERT_TYPE_RAPID_TRANSACTIONS,
    ALERT_TYPE_SANCTIONS_LIST_UPDATE,
    ALERT_TYPE_SANCTIONS_MATCH,
    ALERT_TYPE_STRUCTURING,
    ALERT_TYPE_TERRORISM_FINANCING,
    ESCALATION_TIMEFRAME_1_HOUR,
    ESCALATION_TIMEFRAME_IF_CONCERNS,
    ESCALATION_TIMEFRAME_IMMEDIATE,
    ESCALATION_TIMEFRAME_SAME_DAY,
    PROCEDURE_PRIORITY_CRITICAL,
    PROCEDURE_PRIORITY_HIGH,
    PROCEDURE_PRIORITY_LOW,
    PROCEDURE_PRIORITY_MEDIUM,
    SMR_REQUIREMENT_ASSESS,
    SMR_REQUIREMENT_LIKELY,
    SMR_REQUIREMENT_MANDATORY,
    SMR_REQUIREMENT_UNLIKELY,
)
from compliance.models import AlertProcedureStep, AlertProcedureTemplate


class Command(BaseCommand):
    help = "Sync alert procedure templates to the database (idempotent)"

    def handle(self, *args, **options):
        verbosity = options.get("verbosity", 1)

        templates = self.get_templates()
        valid_alert_types = {t["alert_type"] for t in templates}

        created_count = 0
        updated_count = 0
        steps_created = 0
        steps_updated = 0

        with transaction.atomic():
            for template_data in templates:
                steps_data = template_data.pop("steps", [])
                alert_type = template_data.pop("alert_type")

                obj, created = AlertProcedureTemplate.objects.update_or_create(
                    alert_type=alert_type,
                    defaults=template_data,
                )

                if created:
                    created_count += 1
                    if verbosity >= 2:
                        self.stdout.write(f"  Created template: {alert_type} - {obj.name}")
                else:
                    updated_count += 1
                    if verbosity >= 2:
                        self.stdout.write(f"  Updated template: {alert_type} - {obj.name}")

                # Sync steps for this template
                valid_step_orders = set()
                for step_data in steps_data:
                    order = step_data.pop("order")
                    valid_step_orders.add(order)

                    step_obj, step_created = AlertProcedureStep.objects.update_or_create(
                        template=obj,
                        order=order,
                        defaults=step_data,
                    )

                    if step_created:
                        steps_created += 1
                        if verbosity >= 3:
                            self.stdout.write(f"    Created step {order}: {step_obj.description[:50]}")
                    else:
                        steps_updated += 1
                        if verbosity >= 3:
                            self.stdout.write(f"    Updated step {order}: {step_obj.description[:50]}")

                # Remove obsolete steps for this template
                obsolete_steps = obj.steps.exclude(order__in=valid_step_orders)
                if obsolete_steps.exists():
                    if verbosity >= 2:
                        for step in obsolete_steps:
                            self.stdout.write(f"    Deleted step {step.order}: {step.description[:50]}")
                    obsolete_steps.delete()

            # Remove templates not in the defined list
            obsolete_templates = AlertProcedureTemplate.objects.exclude(alert_type__in=valid_alert_types)
            deleted_count = obsolete_templates.count()
            if deleted_count > 0:
                if verbosity >= 2:
                    for template in obsolete_templates:
                        self.stdout.write(f"  Deleted template: {template.alert_type} - {template.name}")
                obsolete_templates.delete()

        if verbosity >= 1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Templates: {created_count} created, {updated_count} updated, {deleted_count} deleted | "
                    f"Steps: {steps_created} created, {steps_updated} updated"
                )
            )

    def get_templates(self):
        """Return list of all procedure templates with their steps."""
        return [
            # =================================================================
            # CRITICAL PRIORITY ALERTS (A01-A03)
            # =================================================================
            {
                "alert_type": ALERT_TYPE_SANCTIONS_MATCH,
                "name": "Sanctions Match",
                "description": "Transaction or customer matches a name on DFAT or UN sanctions list",
                "priority": PROCEDURE_PRIORITY_CRITICAL,
                "response_time_hours": 1,
                "policy_references": ["Doc 3 §7", "Doc 5 §12"],
                "smr_requirement": SMR_REQUIREMENT_MANDATORY,
                "smr_timeframe_hours": 24,
                "escalation_required": True,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IMMEDIATE,
                "customer_notification_allowed": False,
                "required_documentation": [
                    "Match details (name, DOB, list matched)",
                    "Confirmation of match (not false positive)",
                    "Date and time of identification",
                    "Account suspension record",
                    "Fiat freeze confirmation",
                    "Director notification record",
                    "SMR copy with AUSTRAC reference number",
                    "Authority notification record",
                ],
                "outcome_options": [
                    "Confirmed match: Maintain suspension, await authority direction, terminate",
                    "False positive: Document confirmation methodology, reinstate account",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Verify match is confirmed (not false positive)", "is_required": True},
                    {"order": 2, "description": "Suspend account immediately", "is_required": True},
                    {"order": 3, "description": "Freeze any pending fiat transactions", "is_required": True},
                    {"order": 4, "description": "Escalate to Director", "is_required": True},
                    {"order": 5, "description": "Do NOT notify customer (tipping-off risk)", "is_required": True},
                    {"order": 6, "description": "Prepare SMR", "is_required": True},
                    {"order": 7, "description": "Obtain Director approval for SMR", "is_required": True},
                    {"order": 8, "description": "Lodge SMR within 24 hours", "is_required": True},
                    {"order": 9, "description": "Notify relevant authorities as required", "is_required": True},
                    {"order": 10, "description": "Document all actions taken", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_LAW_ENFORCEMENT,
                "name": "Law Enforcement Inquiry",
                "description": "Inquiry received from law enforcement or regulatory agency",
                "priority": PROCEDURE_PRIORITY_CRITICAL,
                "response_time_hours": 1,
                "policy_references": ["Doc 5 §6.4"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": True,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IMMEDIATE,
                "customer_notification_allowed": False,
                "required_documentation": [
                    "Inquiry details (date, time, agency, officer name, badge/ID, reference number)",
                    "Director notification record",
                    "Records provided to law enforcement",
                    "Any legal process documentation (warrant, subpoena)",
                    "Customer profile review notes",
                    "Suspension decision and rationale (if applicable)",
                    "SMR reference (if lodged)",
                ],
                "outcome_options": [
                    "Records provided, no further action: Document and continue monitoring",
                    "Suspension warranted: Suspend account, prepare SMR if applicable",
                    "Ongoing cooperation required: Maintain records, respond to follow-up requests",
                ],
                "is_active": True,
                "steps": [
                    {
                        "order": 1,
                        "description": "Document inquiry details (date, agency, officer, reference)",
                        "is_required": True,
                    },
                    {"order": 2, "description": "Notify Director immediately", "is_required": True},
                    {"order": 3, "description": "Do NOT notify customer (tipping-off risk)", "is_required": True},
                    {"order": 4, "description": "Cooperate with lawful requests", "is_required": True},
                    {"order": 5, "description": "Conduct full customer profile review", "is_required": True},
                    {"order": 6, "description": "Prepare requested records", "is_required": True},
                    {"order": 7, "description": "Consider account suspension", "is_required": False},
                    {"order": 8, "description": "Prepare SMR if not already lodged", "is_required": False},
                    {"order": 9, "description": "Maintain confidentiality", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_TERRORISM_FINANCING,
                "name": "Terrorism Financing Indicators",
                "description": "Transaction or activity patterns indicative of terrorism financing",
                "priority": PROCEDURE_PRIORITY_CRITICAL,
                "response_time_hours": 1,
                "policy_references": ["Doc 3 §6.3", "Doc 5 §11.1", "Doc 5 §13.1"],
                "smr_requirement": SMR_REQUIREMENT_MANDATORY,
                "smr_timeframe_hours": 24,
                "escalation_required": True,
                "escalation_timeframe": ESCALATION_TIMEFRAME_1_HOUR,
                "customer_notification_allowed": False,
                "required_documentation": [
                    "Description of TF indicators identified",
                    "Transaction details triggering alert",
                    "Customer profile and verification records",
                    "Account suspension record",
                    "Director escalation record",
                    "SMR copy with AUSTRAC reference number",
                    "Authority notification (if applicable)",
                ],
                "outcome_options": [
                    "TF suspicion formed: SMR (24hr), suspend, possible authority notification, terminate",
                    "Indicators explainable: Document thoroughly, enhanced monitoring, consider SMR anyway",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Assess indicators and severity", "is_required": True},
                    {"order": 2, "description": "Suspend account immediately", "is_required": True},
                    {"order": 3, "description": "Escalate to Director within 1 hour", "is_required": True},
                    {"order": 4, "description": "Freeze any pending fiat transactions", "is_required": True},
                    {"order": 5, "description": "Do NOT notify customer", "is_required": True},
                    {
                        "order": 6,
                        "description": "Gather transaction details and customer information",
                        "is_required": True,
                    },
                    {"order": 7, "description": "Prepare SMR immediately", "is_required": True},
                    {"order": 8, "description": "Obtain Director approval", "is_required": True},
                    {"order": 9, "description": "Lodge SMR within 24 hours", "is_required": True},
                    {"order": 10, "description": "Consider authority notification", "is_required": True},
                ],
            },
            # =================================================================
            # HIGH PRIORITY ALERTS (A04-A12, A22)
            # =================================================================
            {
                "alert_type": ALERT_TYPE_ADVERSE_MEDIA_SERIOUS,
                "name": "Adverse Media - Serious",
                "description": "Serious adverse media identified involving crime, ML, TF, or fraud allegations",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 24,
                "policy_references": ["Doc 5 §6.3"],
                "smr_requirement": SMR_REQUIREMENT_LIKELY,
                "smr_timeframe_hours": 72,
                "escalation_required": True,
                "escalation_timeframe": ESCALATION_TIMEFRAME_SAME_DAY,
                "customer_notification_allowed": False,
                "required_documentation": [
                    "Media source details (publication, date, URL)",
                    "Match confirmation (correct customer)",
                    "Summary of allegations",
                    "Credibility assessment",
                    "Transaction history review",
                    "Director escalation record",
                    "Decision and rationale",
                    "SMR reference (if lodged)",
                ],
                "outcome_options": [
                    "False match: Document, continue standard monitoring",
                    "Unconfirmed minor: Enhanced monitoring, document",
                    "Serious allegations: Suspend, investigate, SMR, consider termination",
                    "Confirmed criminal: Terminate, SMR, authority notification",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Review media source and assess credibility", "is_required": True},
                    {"order": 2, "description": "Determine if match is correct customer", "is_required": True},
                    {
                        "order": 3,
                        "description": "Categorize allegation type (crime, ML, TF, fraud, other)",
                        "is_required": True,
                    },
                    {"order": 4, "description": "Review customer transaction history", "is_required": True},
                    {
                        "order": 5,
                        "description": "Assess whether allegations are confirmed or unconfirmed",
                        "is_required": True,
                    },
                    {"order": 6, "description": "Suspend account if serious allegations", "is_required": False},
                    {"order": 7, "description": "Escalate to Director", "is_required": True},
                    {"order": 8, "description": "Prepare SMR if reasonable grounds", "is_required": False},
                    {"order": 9, "description": "Consider account termination", "is_required": False},
                ],
            },
            {
                "alert_type": ALERT_TYPE_HIGH_RISK_WALLET,
                "name": "High-Risk Wallet Address",
                "description": "Transaction involving blockchain address flagged by analytics as high-risk",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 24,
                "policy_references": ["Doc 3 §3.3", "Doc 5 §3.3"],
                "smr_requirement": SMR_REQUIREMENT_LIKELY,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Blockchain analytics report/flag details",
                    "Wallet address(es) involved",
                    "Transaction ID(s)",
                    "Risk category and severity",
                    "Customer profile review",
                    "Customer explanation (if obtained)",
                    "Decision and rationale",
                    "SMR reference (if lodged)",
                ],
                "outcome_options": [
                    "Low-risk flag, explainable: Document, continue monitoring",
                    "Moderate risk: Enhanced monitoring, possible customer contact",
                    "High risk, no explanation: SMR, consider suspension",
                    "Direct illicit involvement: SMR, suspend, possible termination",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Review blockchain analytics flag details", "is_required": True},
                    {
                        "order": 2,
                        "description": "Identify risk category (scam, hack, illicit activity, etc.)",
                        "is_required": True,
                    },
                    {
                        "order": 3,
                        "description": "Determine transaction direction (inbound/outbound)",
                        "is_required": True,
                    },
                    {"order": 4, "description": "Review customer profile and transaction history", "is_required": True},
                    {"order": 5, "description": "Assess customer's explanation (if any)", "is_required": False},
                    {"order": 6, "description": "Consider requesting explanation from customer", "is_required": False},
                    {"order": 7, "description": "Assess for SMR grounds", "is_required": True},
                    {
                        "order": 8,
                        "description": "Escalate to Director if SMR or suspension warranted",
                        "is_required": False,
                    },
                    {"order": 9, "description": "Document decision and rationale", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_MIXER_TUMBLER,
                "name": "Mixer/Tumbler Involvement",
                "description": "Transaction involving cryptocurrency mixing or tumbling service",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 24,
                "policy_references": ["Doc 3 §3.3", "Doc 5 §3.3"],
                "smr_requirement": SMR_REQUIREMENT_LIKELY,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Mixer/tumbler identification details",
                    "Transaction ID(s) and amounts",
                    "Blockchain analytics evidence",
                    "Customer profile review",
                    "Transaction history analysis",
                    "Customer explanation (if obtained)",
                    "Decision and rationale",
                    "SMR reference (if lodged)",
                ],
                "outcome_options": [
                    "Single instance, explained: Document, enhanced monitoring",
                    "Pattern of mixer use: SMR, suspension, possible termination",
                    "No legitimate explanation: SMR, suspend, consider termination",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Confirm mixer/tumbler identification", "is_required": True},
                    {"order": 2, "description": "Identify specific mixing service if known", "is_required": False},
                    {"order": 3, "description": "Determine transaction direction and amount", "is_required": True},
                    {"order": 4, "description": "Review customer profile and stated purpose", "is_required": True},
                    {"order": 5, "description": "Review full transaction history for patterns", "is_required": True},
                    {
                        "order": 6,
                        "description": "Assess customer's prior activity (first instance vs. pattern)",
                        "is_required": True,
                    },
                    {"order": 7, "description": "Consider requesting explanation from customer", "is_required": False},
                    {"order": 8, "description": "Assess for SMR grounds", "is_required": True},
                    {"order": 9, "description": "Escalate to Director if warranted", "is_required": False},
                ],
            },
            {
                "alert_type": ALERT_TYPE_DARKNET_ASSOCIATION,
                "name": "Darknet Association",
                "description": "Transaction involving address associated with darknet marketplace",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 24,
                "policy_references": ["Doc 3 §3.3", "Doc 5 §3.3"],
                "smr_requirement": SMR_REQUIREMENT_MANDATORY,
                "smr_timeframe_hours": 72,
                "escalation_required": True,
                "escalation_timeframe": ESCALATION_TIMEFRAME_SAME_DAY,
                "customer_notification_allowed": False,
                "required_documentation": [
                    "Darknet association evidence",
                    "Transaction ID(s) and amounts",
                    "Blockchain analytics report",
                    "Customer profile",
                    "Transaction history",
                    "SMR copy with AUSTRAC reference",
                    "Director approval record",
                    "Suspension/termination decision",
                ],
                "outcome_options": [
                    "Confirmed darknet association: SMR, terminate, document",
                    "Indirect association (downstream): SMR, assess for termination",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Confirm darknet marketplace identification", "is_required": True},
                    {"order": 2, "description": "Identify specific marketplace if known", "is_required": False},
                    {
                        "order": 3,
                        "description": "Determine transaction details (direction, amount, date)",
                        "is_required": True,
                    },
                    {"order": 4, "description": "Review customer profile", "is_required": True},
                    {"order": 5, "description": "Review full transaction history", "is_required": True},
                    {"order": 6, "description": "Prepare SMR", "is_required": True},
                    {"order": 7, "description": "Escalate to Director", "is_required": True},
                    {"order": 8, "description": "Obtain Director approval for SMR", "is_required": True},
                    {"order": 9, "description": "Consider suspension/termination", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_RANSOMWARE_ASSOCIATION,
                "name": "Ransomware Association",
                "description": "Transaction involving address associated with ransomware activity",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 24,
                "policy_references": ["Doc 3 §3.3", "AUSTRAC DCE Guide §8"],
                "smr_requirement": SMR_REQUIREMENT_MANDATORY,
                "smr_timeframe_hours": 72,
                "escalation_required": True,
                "escalation_timeframe": ESCALATION_TIMEFRAME_SAME_DAY,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Ransomware address details",
                    "Transaction ID(s) and amounts",
                    "Victim/perpetrator assessment",
                    "Customer communication (if any)",
                    "Customer profile",
                    "SMR copy with AUSTRAC reference",
                    "Director approval record",
                    "Law enforcement notification (if applicable)",
                ],
                "outcome_options": [
                    "Customer is victim: SMR (include victim details and perpetrator info), continue relationship",
                    "Customer is perpetrator: SMR, terminate, consider authority notification",
                    "Unclear: SMR, enhanced monitoring, further investigation",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Confirm ransomware address identification", "is_required": True},
                    {
                        "order": 2,
                        "description": "Determine customer role (victim vs. perpetrator)",
                        "is_required": True,
                    },
                    {"order": 3, "description": "Review transaction details", "is_required": True},
                    {"order": 4, "description": "Review customer profile and history", "is_required": True},
                    {"order": 5, "description": "Contact customer to assess if victim", "is_required": False},
                    {
                        "order": 6,
                        "description": "Prepare SMR (required regardless of victim/perpetrator)",
                        "is_required": True,
                    },
                    {"order": 7, "description": "Escalate to Director", "is_required": True},
                    {"order": 8, "description": "Consider law enforcement notification", "is_required": False},
                ],
            },
            {
                "alert_type": ALERT_TYPE_STRUCTURING,
                "name": "Structuring Pattern",
                "description": "Pattern of transactions just below reporting threshold suggesting structuring",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 24,
                "policy_references": ["Doc 3 §3.1", "Doc 5 §3.2"],
                "smr_requirement": SMR_REQUIREMENT_LIKELY,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Transaction list (dates, amounts, types)",
                    "Pattern analysis showing structuring indicators",
                    "Customer profile review",
                    "Historical transaction analysis",
                    "Customer explanation (if obtained)",
                    "Assessment of whether structuring is intentional",
                    "Decision and rationale",
                    "SMR reference (if lodged)",
                ],
                "outcome_options": [
                    "Pattern explainable, legitimate: Document explanation, enhanced monitoring",
                    "Likely intentional structuring: SMR, consider suspension",
                    "Clear structuring, no explanation: SMR, suspend, consider termination",
                ],
                "is_active": True,
                "steps": [
                    {
                        "order": 1,
                        "description": "Confirm structuring pattern (transactions, amounts, timing)",
                        "is_required": True,
                    },
                    {"order": 2, "description": "Review customer profile and stated purpose", "is_required": True},
                    {"order": 3, "description": "Review historical transaction patterns", "is_required": True},
                    {
                        "order": 4,
                        "description": "Assess whether pattern indicates threshold avoidance",
                        "is_required": True,
                    },
                    {"order": 5, "description": "Consider requesting explanation from customer", "is_required": False},
                    {"order": 6, "description": "Assess customer explanation (if provided)", "is_required": False},
                    {"order": 7, "description": "Determine if SMR grounds exist", "is_required": True},
                    {"order": 8, "description": "Escalate to Director if SMR warranted", "is_required": False},
                ],
            },
            {
                "alert_type": ALERT_TYPE_NEW_CUSTOMER_SOF,
                "name": "High-Value Transaction (New Customer)",
                "description": "Transaction >= AUD 10,000 by customer within first 30 days",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 24,
                "policy_references": ["Doc 5 §7.2"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Transaction details",
                    "Customer verification status",
                    "SOF documents (if collected)",
                    "SOF assessment",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "SOF acceptable: Approve transaction, update file",
                    "SOF incomplete: Request additional documents, hold transaction",
                    "SOF raises concerns: Escalate to Director, investigate",
                    "Customer refuses SOF: Consider suspension, assess for SMR",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Verify transaction exceeds guidance threshold", "is_required": True},
                    {"order": 2, "description": "Review customer verification status", "is_required": True},
                    {"order": 3, "description": "Check if SOF documents on file", "is_required": True},
                    {"order": 4, "description": "Assess SOF documents (if on file)", "is_required": False},
                    {
                        "order": 5,
                        "description": "Request SOF documents (if not on file or insufficient)",
                        "is_required": False,
                    },
                    {"order": 6, "description": "Review documents when received", "is_required": False},
                    {"order": 7, "description": "Assess consistency with customer profile", "is_required": True},
                    {"order": 8, "description": "Make approval/hold/reject decision", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_PEP_LIMIT_BREACH,
                "name": "PEP Hard Limit Breach",
                "description": "Domestic PEP transaction exceeds hard limits (single/daily/monthly)",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 1,
                "policy_references": ["Doc 5 §3.4", "Doc 5 §7.1"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": True,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IMMEDIATE,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "PEP verification details",
                    "Limit breach details (type, amount attempted)",
                    "Transaction block confirmation",
                    "Director notification record",
                    "Activity review notes",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "Accidental breach attempt: Document, remind customer of limits",
                    "Repeated breach attempts: Enhanced monitoring, consider SMR",
                    "Pattern of limit testing: SMR, consider termination",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Confirm PEP status", "is_required": True},
                    {"order": 2, "description": "Verify limit breach type (single/daily/monthly)", "is_required": True},
                    {"order": 3, "description": "Block transaction (system should auto-block)", "is_required": True},
                    {"order": 4, "description": "Escalate to Director", "is_required": True},
                    {"order": 5, "description": "Review customer's recent activity", "is_required": True},
                    {"order": 6, "description": "Assess for suspicious patterns", "is_required": True},
                    {"order": 7, "description": "Document incident", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_RAPID_TRANSACTIONS,
                "name": "Rapid Transaction Velocity",
                "description": "5 or more transactions within 1 hour",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 1,
                "policy_references": ["Doc 5 §3.2"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Transaction list with timestamps",
                    "Layering analysis",
                    "Customer profile review",
                    "Automation assessment",
                    "Customer explanation (if obtained)",
                    "Decision and rationale",
                    "SMR reference (if lodged)",
                ],
                "outcome_options": [
                    "Legitimate rapid activity: Document explanation, continue monitoring",
                    "Possible layering: SMR, suspend, investigate further",
                    "Clear layering pattern: SMR, suspend, consider termination",
                ],
                "is_active": True,
                "steps": [
                    {
                        "order": 1,
                        "description": "Review transaction details (amounts, types, destinations)",
                        "is_required": True,
                    },
                    {"order": 2, "description": "Assess for layering indicators", "is_required": True},
                    {"order": 3, "description": "Review customer profile and usual patterns", "is_required": True},
                    {
                        "order": 4,
                        "description": "Check for automation indicators (API usage, identical timing)",
                        "is_required": False,
                    },
                    {"order": 5, "description": "Consider suspension pending investigation", "is_required": False},
                    {
                        "order": 6,
                        "description": "Request explanation from customer if appropriate",
                        "is_required": False,
                    },
                    {"order": 7, "description": "Assess for SMR grounds", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_MULTIPLE_ALERTS,
                "name": "Multiple Alerts (3+) Same Customer",
                "description": "Customer has triggered 3 or more alerts requiring holistic review",
                "priority": PROCEDURE_PRIORITY_HIGH,
                "response_time_hours": 8,
                "policy_references": ["Doc 5 §13.1"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": True,
                "escalation_timeframe": ESCALATION_TIMEFRAME_SAME_DAY,
                "customer_notification_allowed": False,
                "required_documentation": [
                    "Alert compilation (all alerts, dates, types)",
                    "Pattern analysis",
                    "Comprehensive profile review",
                    "Transaction history analysis",
                    "Director escalation record",
                    "Holistic risk assessment",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "Alerts unrelated, individually resolved: Document, enhanced monitoring",
                    "Pattern indicates elevated risk: Enhanced monitoring, consider SMR",
                    "Pattern indicates ML/TF concern: SMR, suspend, consider termination",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Compile all alerts for customer", "is_required": True},
                    {"order": 2, "description": "Analyze alert pattern (types, timing, severity)", "is_required": True},
                    {"order": 3, "description": "Review customer profile comprehensively", "is_required": True},
                    {"order": 4, "description": "Review full transaction history", "is_required": True},
                    {"order": 5, "description": "Escalate to Director", "is_required": True},
                    {"order": 6, "description": "Assess whether SMR grounds exist", "is_required": True},
                    {"order": 7, "description": "Consider suspension pending investigation", "is_required": False},
                    {"order": 8, "description": "Make holistic risk assessment", "is_required": True},
                ],
            },
            # =================================================================
            # MEDIUM PRIORITY ALERTS (A13-A20)
            # =================================================================
            {
                "alert_type": ALERT_TYPE_HIGH_AGGREGATE_VOLUME,
                "name": "High Aggregate Volume",
                "description": "Cumulative transaction volume >= AUD 50,000 in 30 days",
                "priority": PROCEDURE_PRIORITY_MEDIUM,
                "response_time_hours": 72,
                "policy_references": ["Doc 5 §3.2", "Doc 5 §7.4"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Transaction list for review period",
                    "Pattern analysis",
                    "Customer profile comparison",
                    "SOF review/request",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "Consistent with profile, SOF adequate: Document, continue monitoring",
                    "Inconsistent, needs explanation: Request SOF, enhanced monitoring",
                    "Suspicious patterns identified: Investigate further, consider SMR",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Review transaction history for the period", "is_required": True},
                    {
                        "order": 2,
                        "description": "Assess pattern for reasonableness against profile",
                        "is_required": True,
                    },
                    {"order": 3, "description": "Review stated source of funds", "is_required": True},
                    {"order": 4, "description": "Check if SOF documents on file", "is_required": True},
                    {
                        "order": 5,
                        "description": "Request SOF documentation if not on file or insufficient",
                        "is_required": False,
                    },
                    {"order": 6, "description": "Assess any unusual patterns", "is_required": True},
                    {"order": 7, "description": "Document review and decision", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_LARGE_TRANSACTION,
                "name": "High-Value Transaction (Established Customer)",
                "description": "Transaction >= AUD 10,000 by established customer",
                "priority": PROCEDURE_PRIORITY_MEDIUM,
                "response_time_hours": 24,
                "policy_references": ["Doc 5 §7.3"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Transaction details",
                    "SOF review",
                    "Profile consistency assessment",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "Consistent with profile: Approve, document",
                    "Minor inconsistency: Approve, enhanced monitoring",
                    "Material inconsistency: Request explanation, hold if needed",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Review transaction details", "is_required": True},
                    {"order": 2, "description": "Check SOF documents on file", "is_required": True},
                    {"order": 3, "description": "Assess consistency with customer profile", "is_required": True},
                    {"order": 4, "description": "Compare to historical transaction patterns", "is_required": True},
                    {"order": 5, "description": "Request explanation if inconsistent", "is_required": False},
                    {"order": 6, "description": "Document review", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_PATTERN_DEVIATION,
                "name": "Material Pattern Deviation",
                "description": "Transaction activity 3x or more the customer's 90-day average",
                "priority": PROCEDURE_PRIORITY_MEDIUM,
                "response_time_hours": 72,
                "policy_references": ["Doc 5 §3.2"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Deviation analysis (current vs. historical)",
                    "Customer profile review",
                    "Legitimate explanation assessment",
                    "Customer communication (if any)",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "Deviation explained: Document, update profile if needed",
                    "Unexplained but not suspicious: Enhanced monitoring, consider customer contact",
                    "Suspicious deviation: Investigate further, consider SMR",
                ],
                "is_active": True,
                "steps": [
                    {
                        "order": 1,
                        "description": "Review deviation details (volume, frequency, types)",
                        "is_required": True,
                    },
                    {"order": 2, "description": "Compare to customer's historical baseline", "is_required": True},
                    {"order": 3, "description": "Review customer profile and stated purpose", "is_required": True},
                    {"order": 4, "description": "Assess for legitimate explanations", "is_required": True},
                    {"order": 5, "description": "Consider requesting explanation from customer", "is_required": False},
                    {"order": 6, "description": "Assess for suspicious indicators", "is_required": True},
                    {"order": 7, "description": "Document decision", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_ADVERSE_MEDIA_MINOR,
                "name": "Adverse Media - Minor",
                "description": "Minor or unconfirmed adverse media identified",
                "priority": PROCEDURE_PRIORITY_MEDIUM,
                "response_time_hours": 72,
                "policy_references": ["Doc 5 §6.3"],
                "smr_requirement": SMR_REQUIREMENT_UNLIKELY,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Media source details",
                    "Match confirmation",
                    "Allegation summary",
                    "Severity assessment",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "False match: Document, continue standard monitoring",
                    "Minor allegations, unconfirmed: Enhanced monitoring, document",
                    "Concerns escalate: Upgrade to A04 (Serious Adverse Media)",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Review media source and assess credibility", "is_required": True},
                    {"order": 2, "description": "Confirm match is correct customer", "is_required": True},
                    {"order": 3, "description": "Categorize allegation type and severity", "is_required": True},
                    {"order": 4, "description": "Review customer transaction history", "is_required": True},
                    {"order": 5, "description": "Assess whether enhanced monitoring warranted", "is_required": True},
                    {"order": 6, "description": "Document findings and decision", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_INFO_DISCREPANCY,
                "name": "Customer Information Discrepancy",
                "description": "Discrepancy identified in customer verification information",
                "priority": PROCEDURE_PRIORITY_MEDIUM,
                "response_time_hours": 24,
                "policy_references": ["Doc 4 §8", "Doc 5 §6.2"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Discrepancy details",
                    "Verification records review",
                    "Error vs. fraud assessment",
                    "Customer communication",
                    "Resolution documentation",
                ],
                "outcome_options": [
                    "Administrative error: Correct records, document",
                    "Customer error: Request correction, update records",
                    "Suspected fraud: Escalate, suspend, SMR, possible termination",
                ],
                "is_active": True,
                "steps": [
                    {
                        "order": 1,
                        "description": "Identify discrepancy type (name, DOB, address, documents)",
                        "is_required": True,
                    },
                    {"order": 2, "description": "Review verification records", "is_required": True},
                    {"order": 3, "description": "Assess likelihood of error vs. fraud", "is_required": True},
                    {"order": 4, "description": "Request clarification/documents from customer", "is_required": False},
                    {"order": 5, "description": "Verify corrected information", "is_required": False},
                    {"order": 6, "description": "Assess for identity fraud indicators", "is_required": True},
                    {"order": 7, "description": "Escalate to Director if fraud suspected", "is_required": False},
                ],
            },
            {
                "alert_type": ALERT_TYPE_FAILED_DOCUMENTATION,
                "name": "Failed Documentation Request",
                "description": "Customer failed to provide requested documentation within deadline",
                "priority": PROCEDURE_PRIORITY_MEDIUM,
                "response_time_hours": 24,
                "policy_references": ["Doc 5 §8.4"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Original request details and date",
                    "Reminder confirmation",
                    "Customer communication attempts",
                    "Suspension record",
                    "Assessment of suspicious indicators",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "Documents received late: Review, consider reinstatement",
                    "Non-responsive, not suspicious: Maintain suspension, possible termination",
                    "Refusal appears suspicious: SMR, terminate",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Verify deadline has passed", "is_required": True},
                    {"order": 2, "description": "Confirm reminder was sent (3-day extension)", "is_required": True},
                    {"order": 3, "description": "Review customer communication history", "is_required": True},
                    {"order": 4, "description": "Assess reason for non-compliance (if known)", "is_required": False},
                    {"order": 5, "description": "Suspend account", "is_required": True},
                    {"order": 6, "description": "Assess whether refusal is suspicious", "is_required": True},
                    {"order": 7, "description": "Consider SMR if suspicious", "is_required": False},
                    {"order": 8, "description": "Consider termination if continued refusal", "is_required": False},
                ],
            },
            {
                "alert_type": ALERT_TYPE_DORMANT_REACTIVATION,
                "name": "Dormant Account Reactivation",
                "description": "Significant transaction after 90+ days of account inactivity",
                "priority": PROCEDURE_PRIORITY_MEDIUM,
                "response_time_hours": 24,
                "policy_references": ["Doc 5 §3.2"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Dormancy period details",
                    "Reactivating transaction details",
                    "Historical comparison",
                    "Profile review",
                    "Decision and rationale",
                ],
                "outcome_options": [
                    "Activity consistent with historical: Document, continue monitoring",
                    "Unusual but explainable: Enhanced monitoring",
                    "Suspicious reactivation: Investigate further, consider SMR",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Review reactivating transaction details", "is_required": True},
                    {"order": 2, "description": "Compare to customer's historical activity", "is_required": True},
                    {"order": 3, "description": "Review customer profile and verification status", "is_required": True},
                    {
                        "order": 4,
                        "description": "Assess whether activity is consistent with profile",
                        "is_required": True,
                    },
                    {
                        "order": 5,
                        "description": "Consider re-verification if significant time elapsed",
                        "is_required": False,
                    },
                    {"order": 6, "description": "Document assessment", "is_required": True},
                ],
            },
            {
                "alert_type": ALERT_TYPE_SANCTIONS_LIST_UPDATE,
                "name": "New Sanctions List Publication",
                "description": "DFAT or UN sanctions list has been updated, requiring customer re-screening",
                "priority": PROCEDURE_PRIORITY_MEDIUM,
                "response_time_hours": 120,
                "policy_references": ["Doc 3 §7.1", "Doc 5 §9.1"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 24,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": False,
                "required_documentation": [
                    "List update details (DFAT/UN, date, changes)",
                    "Re-screening completion confirmation",
                    "Any matches identified",
                    "Match investigation outcomes",
                    "Completion record",
                ],
                "outcome_options": [
                    "No matches: Document completion, continue",
                    "Potential matches found: Investigate per initial screening procedures",
                    "Confirmed match found: Follow A01 (Sanctions Match) procedure",
                ],
                "is_active": True,
                "steps": [
                    {"order": 1, "description": "Confirm list update received", "is_required": True},
                    {
                        "order": 2,
                        "description": "Initiate batch re-screening of all active customers",
                        "is_required": True,
                    },
                    {"order": 3, "description": "Review any potential matches", "is_required": True},
                    {"order": 4, "description": "Investigate potential matches", "is_required": False},
                    {"order": 5, "description": "Escalate confirmed matches per A01", "is_required": False},
                    {"order": 6, "description": "Document re-screening completion", "is_required": True},
                ],
            },
            # =================================================================
            # LOW PRIORITY ALERTS (A21)
            # =================================================================
            {
                "alert_type": ALERT_TYPE_PERIODIC_REVIEW,
                "name": "Periodic Review Due",
                "description": "Customer due for periodic review based on risk rating schedule",
                "priority": PROCEDURE_PRIORITY_LOW,
                "response_time_hours": 168,
                "policy_references": ["Doc 5 §5"],
                "smr_requirement": SMR_REQUIREMENT_ASSESS,
                "smr_timeframe_hours": 72,
                "escalation_required": False,
                "escalation_timeframe": ESCALATION_TIMEFRAME_IF_CONCERNS,
                "customer_notification_allowed": True,
                "required_documentation": [
                    "Information verification",
                    "Transaction analysis",
                    "Screening results",
                    "Risk assessment",
                    "Next review date",
                ],
                "outcome_options": [
                    "Continue: No concerns - update review date, standard monitoring",
                    "Enhanced Monitoring: Minor concerns - flag for manual review",
                    "Suspend: Material concerns - suspend pending investigation",
                    "Terminate: Policy violations - exit procedures, consider SMR",
                    "SMR: Reasonable suspicion - lodge SMR, continue or terminate",
                ],
                "is_active": True,
                "steps": [
                    {
                        "order": 1,
                        "description": "Verify customer details current (name, contact, address, occupation, SOF)",
                        "is_required": True,
                    },
                    {
                        "order": 2,
                        "description": "Analyze transaction volume, frequency, patterns vs. profile",
                        "is_required": True,
                    },
                    {
                        "order": 3,
                        "description": "Re-screen against sanctions (DFAT, UN), PEP, adverse media, FATF",
                        "is_required": True,
                    },
                    {
                        "order": 4,
                        "description": "Assess acceptance criteria, patterns, screening results",
                        "is_required": True,
                    },
                    {"order": 5, "description": "Document findings, decision, next review date", "is_required": True},
                ],
            },
        ]
