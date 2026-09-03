import base64
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from compliance.constants import PEP_TYPE_FOREIGN, PEP_TYPE_NONE
from integrations.kyc.base import (
    KYCProvider,
    NormalizedVerificationResult,
    VerificationSession,
)
from integrations.kyc.constants import (
    PROVIDER_KYCAID,
    REVIEW_GREEN,
    REVIEW_RED,
    STATUS_PENDING,
    STATUS_UNUSED,
)

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


def _validate_provider_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    is_local_http = parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS

    if (
        not candidate
        or (parsed.scheme != "https" and not is_local_http)
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ImproperlyConfigured("KYCAID_BASE_URL must be an explicit HTTPS URL (or a local HTTP test endpoint)")
    return candidate


class KYCAIDService(KYCProvider):

    def __init__(self):
        self.api_token = settings.KYCAID_API_TOKEN
        self.base_url = settings.KYCAID_BASE_URL
        self.form_id = settings.KYCAID_FORM_ID

    def get_provider_name(self) -> str:
        return PROVIDER_KYCAID

    def create_applicant(self, external_user_id: str, **profile_data) -> dict:
        body = {
            "type": "PERSON",
            "external_applicant_id": external_user_id,
        }
        if profile_data.get("first_name"):
            body["first_name"] = profile_data["first_name"]
        if profile_data.get("last_name"):
            body["last_name"] = profile_data["last_name"]
        if profile_data.get("dob"):
            body["dob"] = profile_data["dob"]
        if profile_data.get("residence_country"):
            body["residence_country"] = profile_data["residence_country"]
        if profile_data.get("email"):
            body["email"] = profile_data["email"]

        response = self._make_request("POST", "/applicants", data=body)
        applicant_id = response.get("applicant_id") or response.get("id")

        logger.info("Created applicant")
        return {"applicant_id": applicant_id}

    def get_applicant_status(self, applicant_id: str) -> Dict[str, Any]:
        response = self._make_request("GET", f"/applicants/{applicant_id}")
        logger.info("Fetched applicant status")
        return response

    def get_applicant_data(self, applicant_id: str) -> Dict[str, Any]:
        response = self._make_request("GET", f"/applicants/{applicant_id}")
        logger.info("Fetched applicant data")
        return response

    def get_form_url(self, form_id: str, applicant_id: str) -> str:
        if not form_id:
            raise ImproperlyConfigured("KYCAID_FORM_ID is not configured")
        response = self._make_request("POST", f"/forms/{form_id}/urls", data={"applicant_id": applicant_id})
        return response.get("form_url") or response.get("url")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        if not self.api_token:
            logger.warning("Webhook verification is not configured")
            return False

        encoded_body = base64.b64encode(payload)
        expected_signature = hmac.new(self.api_token.encode(), encoded_body, hashlib.sha512).hexdigest()

        is_valid = hmac.compare_digest(expected_signature, signature)

        if not is_valid:
            logger.warning("Invalid webhook signature")

        return is_valid

    def normalize_webhook(self, webhook_data: dict) -> NormalizedVerificationResult:
        verified = webhook_data.get("verified", False)
        status = webhook_data.get("status")

        if verified:
            review_result = REVIEW_GREEN
        elif status is None:
            review_result = ""
        elif status == STATUS_PENDING:
            review_result = ""
        else:
            review_result = REVIEW_RED

        if status is None:
            status = STATUS_UNUSED

        rejection_labels = []
        verifications = webhook_data.get("verifications", {})
        for _check_name, check_data in verifications.items():
            if isinstance(check_data, dict):
                decline_reasons = check_data.get("decline_reasons", [])
                rejection_labels.extend(decline_reasons)

        doc_type = None
        doc_country = None
        doc_verification = verifications.get("document", {})
        if isinstance(doc_verification, dict):
            doc_type = doc_verification.get("type")
            doc_country = doc_verification.get("country")

        applicant = webhook_data.get("applicant", {})
        extracted_data = {}
        if applicant:
            first_name = applicant.get("first_name") or ""
            last_name = applicant.get("last_name") or ""
            full_name = f"{first_name} {last_name}".strip()
            extracted_data = {
                "fullName": full_name if full_name else None,
                "dateOfBirth": applicant.get("dob"),
                "address": self._extract_address(applicant),
                "residenceCountry": applicant.get("residence_country"),
            }

        pep_data = {"pep_type": PEP_TYPE_NONE}
        pep_verification = verifications.get("pep", {})
        if isinstance(pep_verification, dict) and pep_verification.get("verified") is False:
            pep_data = {"pep_type": PEP_TYPE_FOREIGN, "details": pep_verification.get("decline_reasons", [])}

        return NormalizedVerificationResult(
            verification_status=status,
            review_result=review_result,
            is_verified=verified,
            rejection_labels=rejection_labels,
            document_type=doc_type,
            document_country=doc_country,
            pep_data=pep_data,
            extracted_data=extracted_data,
        )

    def extract_verified_data(self, applicant_data: dict) -> dict:
        first_name = applicant_data.get("first_name") or ""
        last_name = applicant_data.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip()

        return {
            "fullName": full_name if full_name else None,
            "dateOfBirth": applicant_data.get("dob"),
            "address": self._extract_address(applicant_data),
            "residenceCountry": applicant_data.get("residence_country"),
        }

    def generate_session(self, applicant_id: str, external_user_id: str) -> VerificationSession:
        form_url = self.get_form_url(self.form_id, applicant_id)
        return VerificationSession(
            provider=PROVIDER_KYCAID,
            applicant_id=applicant_id,
            form_url=form_url,
        )

    @staticmethod
    def _extract_address(applicant_data: dict) -> Optional[str]:
        addresses = applicant_data.get("addresses", [])
        if addresses and isinstance(addresses, list):
            for addr in addresses:
                if isinstance(addr, dict) and addr.get("full_address"):
                    return addr["full_address"]
        return None

    BLOCKCHAIN_TO_ASSET = {
        "ethereum": "ETH",
        "bitcoin": "BTC",
        "litecoin": "LTC",
        "ripple": "XRP",
        "cardano": "ADA",
        "tron": "TRX",
        "solana": "SOL",
        "avalanche": "AVAX",
        "polygon": "MATIC",
        "dogecoin": "DOGE",
        "polkadot": "DOT",
        "algorand": "ALGO",
        "stellar": "XLM",
        "near": "NEAR",
        "tezos": "XTZ",
        "ton": "TON",
        "arbitrum": "ARB",
        "zcash": "ZEC",
    }

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
        callback_url = self._get_crypto_callback_url()

        asset = self.BLOCKCHAIN_TO_ASSET.get(blockchain or "", "ETH")

        body = {
            "hash": to_address,
            "asset": asset,
            "callback_url": callback_url,
        }

        logger.info("Submitting address check")
        response = self._make_request("POST", "/services/crypto/address-verification", data=body)
        logger.info("Address check accepted")

        return response

    def verify_crypto_webhook_signature(self, payload: bytes, signature: str) -> bool:
        return self.verify_webhook_signature(payload, signature)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        if not self.api_token:
            raise ImproperlyConfigured("KYCAID_API_TOKEN is not configured")
        base_url = _validate_provider_url(self.base_url)
        url = f"{base_url}{endpoint}"

        headers = {
            "Authorization": f"Token {self.api_token}",
        }

        kwargs = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": 30,
        }

        if files:
            kwargs["files"] = files
            if data:
                kwargs["data"] = data
        elif data:
            headers["Content-Type"] = "application/json"
            kwargs["json"] = data

        try:
            response = requests.request(**kwargs)
        except requests.RequestException as exc:
            logger.error("Provider request failed")
            raise requests.HTTPError("KYCAID request failed") from exc

        if not response.ok:
            logger.error(f"Provider request failed with HTTP {response.status_code}")
            raise requests.HTTPError(
                f"KYCAID request failed with HTTP {response.status_code}",
                response=response,
            )

        return response.json()

    @staticmethod
    def _get_crypto_callback_url() -> str:
        from django.conf import settings

        base = getattr(settings, "PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")
        return f"{base}/webhooks/kycaid/crypto/"
