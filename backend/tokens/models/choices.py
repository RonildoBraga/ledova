from django.db import models


class ShareTokenStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    DEPLOYING = "deploying", "Deploying"
    DEPLOYED = "deployed", "Deployed"
    PAUSED = "paused", "Paused"


class ShareTokenType(models.TextChoices):
    ORDINARY = "ordinary", "Ordinary"
    PREFERENCE = "preference", "Preference"
    REDEEMABLE = "redeemable", "Redeemable"


class IssuanceStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class IssuanceType(models.TextChoices):
    INITIAL = "initial", "Initial Issuance"
    ADDITIONAL = "additional", "Additional Issuance"
    BONUS = "bonus", "Bonus Shares"
    DIVIDEND = "dividend", "Dividend Reinvestment"
    TRANSFER = "transfer", "Transfer (Re-issuance)"


class RequestStatus(models.TextChoices):
    """Review workflow shared by CapitalIncreaseRequest and ShareIssuanceRequest."""

    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    UNDER_REVIEW = "under_review", "Under Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXECUTING = "executing", "Executing"
    EXECUTED = "executed", "Executed"
    FAILED = "failed", "Failed"


class TransferOrderType(models.TextChoices):
    BUY = "buy", "Buy"
    SELL = "sell", "Sell"


class TransferOrderStatus(models.TextChoices):
    OPEN = "open", "Open"
    PARTIALLY_FILLED = "partially_filled", "Partially Filled"
    MATCHED = "matched", "Matched"
    PENDING_SIGNATURE = "pending_signature", "Pending Signature"
    EXECUTING = "executing", "Executing"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"
    FAILED = "failed", "Failed"


class SwapOrderStatus(models.TextChoices):

    CREATED = "created", "Created"
    SELLER_SIGNED = "seller_signed", "Seller Signed"
    BUYER_SIGNED = "buyer_signed", "Buyer Signed"
    READY = "ready", "Ready for Execution"
    EXECUTING = "executing", "Executing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"
