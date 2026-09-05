import os

from .base import DEBUG

TRANSAK_API_KEY = os.getenv("TRANSAK_API_KEY", "")
TRANSAK_API_SECRET = os.getenv("TRANSAK_API_SECRET", "")
TRANSAK_API_URL = os.getenv("TRANSAK_API_URL", "")
TRANSAK_API_GATEWAY_URL = os.getenv("TRANSAK_API_GATEWAY_URL", "")
TRANSAK_REFERRER_DOMAIN = os.getenv("TRANSAK_REFERRER_DOMAIN", "localhost")
TRANSAK_THEME_COLOR = os.getenv("TRANSAK_THEME_COLOR", "6366f1")

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
COINGECKO_BASE_URL = os.getenv("COINGECKO_BASE_URL") or "https://api.coingecko.com/api/v3"
COINGECKO_TIMEOUT = int(os.getenv("COINGECKO_TIMEOUT", "10"))

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_API_URL = os.getenv("SENDGRID_API_URL", "")
SENDGRID_TIMEOUT = int(os.getenv("SENDGRID_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@localhost")


EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend"
)

KYC_PROVIDER = os.environ.get("KYC_PROVIDER", "")

KYCAID_API_TOKEN = os.environ.get("KYCAID_API_TOKEN", "")
KYCAID_BASE_URL = os.environ.get("KYCAID_BASE_URL", "")
KYCAID_FORM_ID = os.environ.get("KYCAID_FORM_ID", "")
KYCAID_CRYPTO_MONITORING_ENABLED = os.environ.get("KYCAID_CRYPTO_MONITORING_ENABLED", "false").lower() == "true"

SUMSUB_API_KEY = os.environ.get("SUMSUB_API_KEY", "")
SUMSUB_SECRET_KEY = os.environ.get("SUMSUB_SECRET_KEY", "")
SUMSUB_BASE_URL = os.environ.get("SUMSUB_BASE_URL", "")
SUMSUB_LEVEL_NAME = os.environ.get("SUMSUB_LEVEL_NAME", "basic-kyc-level")
SUMSUB_WEBHOOK_SECRET = os.environ.get("SUMSUB_WEBHOOK_SECRET", "")

CRYPTO_RISK_THRESHOLD_MEDIUM = float(os.environ.get("CRYPTO_RISK_THRESHOLD_MEDIUM", "0.25"))
CRYPTO_RISK_THRESHOLD_HIGH = float(os.environ.get("CRYPTO_RISK_THRESHOLD_HIGH", "0.6"))

ALCHEMY_ETH_URL = os.environ.get("ALCHEMY_ETH_URL", "")
ALCHEMY_BTC_URL = os.environ.get("ALCHEMY_BTC_URL", "")
ALCHEMY_BASE_URL = os.environ.get("ALCHEMY_BASE_URL", "")
ALCHEMY_WEBHOOK_SIGNING_KEY = os.environ.get("ALCHEMY_WEBHOOK_SIGNING_KEY", "")

BLOCKSTREAM_API_URL = os.environ.get("BLOCKSTREAM_API_URL", "https://blockstream.info/testnet/api")
BLOCKSTREAM_TIMEOUT = int(os.environ.get("BLOCKSTREAM_TIMEOUT", "30"))


LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://host.docker.internal:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5vl:7b")

LEDOVA_ADMIN_BASE_URL = os.environ.get("LEDOVA_ADMIN_BASE_URL", "http://localhost:5174/admin").rstrip("/")
PUBLIC_API_BASE_URL = os.environ.get("PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")
