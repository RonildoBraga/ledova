import os
import uuid as uuid_lib

from django.conf import settings
from django.db import models

from companies.querysets.document import CompanyDocumentQuerySet
from shared.models import BaseModel


def company_document_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    unique_name = f"{uuid_lib.uuid4()}{ext}"
    return f"companies/{instance.company.uuid}/documents/{instance.document_type}/{unique_name}"


class DocumentType(models.TextChoices):

    CERTIFICATE_OF_INCORPORATION = "cert_inc", "Certificate of Incorporation"
    ASIC_EXTRACT = "asic", "ASIC Company Extract"
    CONSTITUTION = "constitution", "Company Constitution"
    SHARE_REGISTER = "share_register", "Current Share Register"

    FINANCIAL_STATEMENTS = "financials", "Financial Statements"
    AUDITOR_REPORT = "auditor_report", "Auditor Report"

    DIRECTOR_ID = "director_id", "Director Identification"
    BENEFICIAL_OWNERSHIP = "beneficial_ownership", "Beneficial Ownership Declaration"
    SHAREHOLDER_AGREEMENT = "shareholder", "Shareholder Agreement"

    BUSINESS_PLAN = "business_plan", "Business Plan"
    RISK_DISCLOSURE = "risk_disclosure", "Risk Disclosure Statement"

    PROSPECTUS = "prospectus", "Prospectus or Information Memorandum"
    LEGAL_OPINION = "legal_opinion", "Legal Opinion"
    TAX_RETURN = "tax_return", "Tax Return"
    BANK_STATEMENT = "bank_statement", "Bank Statement"
    OTHER = "other", "Other"


LISTING_REQUIRED_DOCUMENTS = [
    DocumentType.CERTIFICATE_OF_INCORPORATION,
    DocumentType.ASIC_EXTRACT,
    DocumentType.CONSTITUTION,
    DocumentType.SHARE_REGISTER,
    DocumentType.FINANCIAL_STATEMENTS,
    DocumentType.DIRECTOR_ID,
    DocumentType.BENEFICIAL_OWNERSHIP,
    DocumentType.BUSINESS_PLAN,
    DocumentType.RISK_DISCLOSURE,
]


class CompanyDocument(BaseModel):
    objects = CompanyDocumentQuerySet.as_manager()

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(
        max_length=30,
        choices=DocumentType.choices,
    )
    name = models.CharField(max_length=255)

    file = models.FileField(
        upload_to=company_document_path,
        null=True,
        blank=True,
        help_text="Uploaded file (preferred)",
    )
    external_url = models.URLField(
        blank=True,
        help_text="External URL if file is stored elsewhere",
    )

    file_size = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=100)

    @property
    def file_url(self):
        if self.file:
            return self.file.url
        return self.external_url

    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)

    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_documents",
    )

    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Company Document"
        verbose_name_plural = "Company Documents"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company.name} - {self.get_document_type_display()}"
