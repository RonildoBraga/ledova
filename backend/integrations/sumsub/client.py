import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from django.conf import settings

from integrations.kyc.base import (
    KYCProvider,
    NormalizedVerificationResult,
    VerificationSession,
)
from integrations.kyc.constants import PROVIDER_SUMSUB, REVIEW_GREEN, STATUS_COMPLETED

logger = logging.getLogger("ledova_backend")


class SumSubService(KYCProvider):

    def __init__(self):
        self.api_key = settings.SUMSUB_API_KEY
        self.secret_key = settings.SUMSUB_SECRET_KEY
        self.base_url = settings.SUMSUB_BASE_URL
        self.level_name = settings.SUMSUB_LEVEL_NAME

    def get_provider_name(self) -> str:
        return PROVIDER_SUMSUB

    def create_applicant(self, external_user_id: str, **profile_data) -> dict:
        body = {"externalUserId": external_user_id}
        if profile_data.get("first_name"):
            body["fixedInfo"] = {"firstName": profile_data["first_name"]}
            if profile_data.get("last_name"):
                body["fixedInfo"]["lastName"] = profile_data["last_name"]
        if profile_data.get("email"):
            body["email"] = profile_data["email"]

        try:
            params = {"levelName": self.level_name}
            result = self._make_request("POST", "/resources/applicants", data=body, params=params)
            applicant_id = result.get("id")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                logger.info(f"[SUMSUB_CLIENT] Applicant already exists for {external_user_id}, fetching existing")
                existing = self.get_applicant_by_external_id(external_user_id)
                applicant_id = existing.get("id")
            else:
                raise

        access_token = self.generate_access_token_for_external_user(external_user_id)
        return {"access_token": access_token, "applicant_id": applicant_id}

    def normalize_webhook(self, webhook_data: dict) -> NormalizedVerificationResult:
        review_result = webhook_data.get("reviewResult", {})
        review_answer = review_result.get("reviewAnswer")
        rejection_labels = review_result.get("rejectLabels", [])
        review_status = webhook_data.get("reviewStatus")

        pep_data = self._extract_pep_data(webhook_data)

        doc_type, doc_country = self._extract_document_info(webhook_data)

        return NormalizedVerificationResult(
            verification_status=review_status or STATUS_COMPLETED,
            review_result=review_answer or "",
            is_verified=review_answer == REVIEW_GREEN,
            rejection_labels=rejection_labels,
            document_type=doc_type,
            document_country=doc_country,
            pep_data=pep_data,
            extracted_data={},
        )

    def extract_verified_data(self, applicant_data: dict) -> dict:
        info = applicant_data.get("info", {})
        addresses = info.get("addresses", [])

        first_name = info.get("firstName", "") or info.get("firstNameEn", "")
        last_name = info.get("lastName", "") or info.get("lastNameEn", "")
        full_name = f"{first_name} {last_name}".strip() if first_name or last_name else None

        address = None
        if addresses and len(addresses) > 0:
            first_address = addresses[0]
            address = first_address.get("formattedAddress")
            if not address:
                parts = []
                if first_address.get("street"):
                    parts.append(first_address.get("street"))
                if first_address.get("town"):
                    parts.append(first_address.get("town"))
                if first_address.get("state"):
                    parts.append(first_address.get("state"))
                if first_address.get("postCode"):
                    parts.append(first_address.get("postCode"))
                if first_address.get("country"):
                    parts.append(first_address.get("country"))
                address = ", ".join(parts) if parts else None

        date_of_birth = info.get("dob")

        return {
            "fullName": full_name,
            "dateOfBirth": date_of_birth,
            "address": address,
        }

    def generate_session(self, applicant_id: str, external_user_id: str) -> VerificationSession:
        access_token = self.generate_access_token_for_external_user(external_user_id)
        return VerificationSession(
            provider=PROVIDER_SUMSUB,
            applicant_id=applicant_id,
            access_token=access_token,
        )

    @staticmethod
    def _extract_pep_data(status_data: Dict[str, Any]) -> Dict[str, Any]:
        from compliance.constants import (
            PEP_TYPE_ASSOCIATE,
            PEP_TYPE_DOMESTIC,
            PEP_TYPE_FAMILY,
            PEP_TYPE_FOREIGN,
            PEP_TYPE_INTERNATIONAL_ORG,
            PEP_TYPE_NONE,
        )

        pep_data = {"pep_type": PEP_TYPE_NONE, "details": None}

        risk_labels = status_data.get("riskLabels", [])
        applicant_risk_labels = status_data.get("applicantRiskLabels", [])
        review_result = status_data.get("reviewResult", {})
        review_risk_labels = review_result.get("riskLabels", [])

        all_labels = risk_labels + applicant_risk_labels + review_risk_labels
        all_labels_lower = [str(label).lower() for label in all_labels if label]

        pep_type = PEP_TYPE_NONE

        for label in all_labels_lower:
            if "family" in label or "relative" in label:
                pep_type = PEP_TYPE_FAMILY
                break
            elif "associate" in label or "close_associate" in label:
                pep_type = PEP_TYPE_ASSOCIATE
                break
            elif "international" in label or "intl_org" in label:
                pep_type = PEP_TYPE_INTERNATIONAL_ORG
                break
            elif "foreign" in label or "foreign_pep" in label:
                pep_type = PEP_TYPE_FOREIGN
                break
            elif "domestic" in label or "domestic_pep" in label:
                pep_type = PEP_TYPE_DOMESTIC
                break
            elif "pep" in label or "politically_exposed" in label:
                pep_type = PEP_TYPE_FOREIGN
                break

        if pep_type != PEP_TYPE_NONE:
            pep_data["pep_type"] = pep_type
            pep_data["details"] = all_labels

        return pep_data

    @staticmethod
    def _extract_document_info(status_data: Dict[str, Any]) -> tuple:
        doc_type = None
        doc_country = None

        fixed_info = status_data.get("fixedInfo", {})
        if fixed_info:
            doc_type = fixed_info.get("idDocType")
            doc_country = fixed_info.get("country")

        if not doc_type or not doc_country:
            info = status_data.get("info", {})
            if info:
                id_docs = info.get("idDocs", [])
                if id_docs and len(id_docs) > 0:
                    first_doc = id_docs[0]
                    doc_type = doc_type or first_doc.get("idDocType")
                    doc_country = doc_country or first_doc.get("country")

                doc_country = doc_country or info.get("country")

        return doc_type, doc_country

    def _generate_signature(self, method: str, url: str, timestamp: str, body: bytes = b"") -> str:
        data = f"{timestamp}{method.upper()}{url}".encode() + body
        signature = hmac.new(self.secret_key.encode(), data, hashlib.sha256).hexdigest()
        return signature

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        url_path = endpoint
        if params:
            query_string = urlencode(sorted(params.items()))
            url_path = f"{endpoint}?{query_string}"

        url = f"{self.base_url}{url_path}"
        timestamp = str(int(time.time()))

        if files:
            session = requests.Session()
            req = requests.Request(method, url, files=files, data=data or {})
            prepared = session.prepare_request(req)

            body = prepared.body or b""
            if isinstance(body, str):
                body = body.encode()

            signature = self._generate_signature(method, url_path, timestamp, body)

            prepared.headers["X-App-Token"] = self.api_key
            prepared.headers["X-App-Access-Sig"] = signature
            prepared.headers["X-App-Access-Ts"] = timestamp

            response = session.send(prepared, timeout=30)
        else:
            body = b""
            if data:
                body = json.dumps(data).encode()

            signature = self._generate_signature(method, url_path, timestamp, body)

            headers = {
                "X-App-Token": self.api_key,
                "X-App-Access-Sig": signature,
                "X-App-Access-Ts": timestamp,
                "Content-Type": "application/json",
            }
            response = requests.request(method=method, url=url, headers=headers, json=data, timeout=30)

        if not response.ok:
            try:
                error_body = response.json()
                logger.error(f"SumSub API Error: {response.status_code} - {error_body}")
            except Exception:
                logger.error(f"SumSub API Error: {response.status_code} - {response.text}")
            response.raise_for_status()

        return response.json()

    def get_applicant_data(self, applicant_id: str) -> Dict[str, Any]:
        endpoint = f"/resources/applicants/{applicant_id}/one"

        logger.info(f"[SUMSUB_CLIENT] Fetching applicant data for {applicant_id} from {self.base_url}{endpoint}")
        response = self._make_request("GET", endpoint)

        logger.info(f"[SUMSUB_CLIENT] Applicant data response for {applicant_id}: {response}")
        return response

    def get_applicant_by_external_id(self, external_user_id: str) -> Dict[str, Any]:
        endpoint = f"/resources/applicants/-;externalUserId={external_user_id}/one"

        logger.info(f"[SUMSUB_CLIENT] Fetching applicant by external ID {external_user_id}")
        response = self._make_request("GET", endpoint)

        logger.info(f"[SUMSUB_CLIENT] Found applicant {response.get('id')} for external ID {external_user_id}")
        return response

    def generate_access_token_for_external_user(self, external_user_id: str, ttl_seconds: int = 1200) -> str:
        params = {"userId": external_user_id, "levelName": self.level_name, "ttlInSecs": str(ttl_seconds)}
        query_string = urlencode(sorted(params.items()))
        endpoint = f"/resources/accessTokens?{query_string}"

        response = self._make_request("POST", endpoint)

        return response.get("token")

    def get_applicant_status(self, applicant_id: str) -> Dict[str, Any]:
        endpoint = f"/resources/applicants/{applicant_id}/status"

        logger.info(f"[SUMSUB_CLIENT] Fetching status for applicant {applicant_id} from {self.base_url}{endpoint}")
        response = self._make_request("GET", endpoint)
        logger.info(f"[SUMSUB_CLIENT] Status response for {applicant_id}: {response}")
        return response

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        if not settings.SUMSUB_WEBHOOK_SECRET:
            logger.warning("SUMSUB_WEBHOOK_SECRET not configured, skipping signature verification")
            return True

        expected_signature = hmac.new(settings.SUMSUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()

        is_valid = hmac.compare_digest(expected_signature, signature)

        if not is_valid:
            logger.warning("Invalid webhook signature")

        return is_valid
