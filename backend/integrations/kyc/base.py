from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from compliance.constants import PEP_TYPE_NONE


@dataclass
class VerificationSession:

    provider: str
    applicant_id: str
    access_token: Optional[str] = None
    form_url: Optional[str] = None


@dataclass
class NormalizedVerificationResult:

    verification_status: str
    review_result: str
    is_verified: bool
    rejection_labels: list = field(default_factory=list)
    document_type: Optional[str] = None
    document_country: Optional[str] = None
    pep_data: dict = field(default_factory=lambda: {"pep_type": PEP_TYPE_NONE})
    extracted_data: dict = field(default_factory=dict)


class KYCProvider(ABC):

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def create_applicant(self, external_user_id: str, **profile_data) -> dict:
        pass

    @abstractmethod
    def get_applicant_status(self, applicant_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_applicant_data(self, applicant_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        pass

    @abstractmethod
    def normalize_webhook(self, webhook_data: dict) -> NormalizedVerificationResult:
        pass

    @abstractmethod
    def generate_session(self, applicant_id: str, external_user_id: str) -> VerificationSession:
        pass

    @abstractmethod
    def extract_verified_data(self, applicant_data: dict) -> dict:
        pass

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
