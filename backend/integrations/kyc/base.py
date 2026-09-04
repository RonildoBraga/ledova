from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from compliance.constants import PEP_TYPE_NONE


@dataclass
class VerificationSession:

    provider: str
    applicant_id: str
    access_token: Optional[str] = None  # Sumsub only
    form_url: Optional[str] = None  # KYCAID only


@dataclass
class NormalizedVerificationResult:

    verification_status: str  # init|pending|completed|onHold
    review_result: str  # GREEN|RED|YELLOW
    is_verified: bool
    rejection_labels: list = field(default_factory=list)
    document_type: Optional[str] = None
    document_country: Optional[str] = None
    pep_data: dict = field(default_factory=lambda: {"pep_type": PEP_TYPE_NONE})
    extracted_data: dict = field(default_factory=dict)


class KYCProvider(ABC):

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider identifier (e.g. 'sumsub', 'kycaid')."""

    @abstractmethod
    def create_applicant(self, external_user_id: str, **profile_data) -> dict:
        """Create an applicant in the KYC provider. Returns dict with at least 'applicant_id'."""

    @abstractmethod
    def get_applicant_status(self, applicant_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_applicant_data(self, applicant_id: str) -> Dict[str, Any]:
        """Get full applicant data including extracted document information."""

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        pass

    @abstractmethod
    def normalize_webhook(self, webhook_data: dict) -> NormalizedVerificationResult:
        """Convert provider-specific webhook/status data to a NormalizedVerificationResult."""

    @abstractmethod
    def generate_session(self, applicant_id: str, external_user_id: str) -> VerificationSession:
        """Generate session credentials (token or form URL) for an existing applicant."""

    @abstractmethod
    def extract_verified_data(self, applicant_data: dict) -> dict:
        """Extract verified profile data (fullName, dateOfBirth, address) from applicant data."""

    def submit_crypto_transaction(
        self,
        applicant_id: str,
        transaction_id: str,
        to_address: str,
        from_address: Optional[str] = None,
        amount: Optional[str] = None,
        currency: Optional[str] = None,
        blockchain: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.get_provider_name()} does not support crypto screening")

    def verify_crypto_webhook_signature(self, payload: bytes, signature: str) -> bool:
        raise NotImplementedError(f"{self.get_provider_name()} does not support crypto screening")
