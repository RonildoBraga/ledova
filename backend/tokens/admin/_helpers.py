import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as ReadTimeout
from decimal import Decimal

from django import forms
from django.utils.html import format_html, format_html_join

logger = logging.getLogger(__name__)

CHAIN_READ_TIMEOUT = 5

BUTTON_STYLE = (
    "display: inline-block; padding: 6px 12px; margin: 2px; "
    "text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;"
)
BADGE_STYLE = "padding: 3px 8px; border-radius: 3px; font-size: 11px;"


def bounded_chain_read(read, label, default=None, timeout=None):
    timeout = CHAIN_READ_TIMEOUT if timeout is None else timeout
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        return executor.submit(read).result(timeout=timeout)
    except ReadTimeout:
        logger.warning(f"{label} not answered within {timeout}s")
        return default
    except Exception as exc:
        logger.warning(f"{label} could not be read: {exc}")
        return default
    finally:
        executor.shutdown(wait=False)


def _colors(color):
    return color if isinstance(color, tuple) else (color, "white")


def _badge(color, label):
    background, text = _colors(color)
    return format_html(
        '<span style="background-color: {}; color: {}; {}">{}</span>', background, text, BADGE_STYLE, label
    )


def status_badge(colors):

    def badge(_admin, obj):
        return _badge(colors.get(obj.status, "#777777"), obj.get_status_display())

    badge.short_description = "Status"
    badge.admin_order_field = "status"
    return badge


def active_badge(_admin, obj):
    return _badge("#28a745" if obj.is_active else "#dc3545", "Active" if obj.is_active else "Inactive")


active_badge.short_description = "Status"


def short_hex(value, head=10, tail=6):
    return f"{value[:head]}...{value[-tail:]}" if value else "-"


def hex_column(field, description, tail=6):

    def column(_admin, obj):
        return short_hex(getattr(obj, field), tail=tail)

    column.short_description = description
    return column


def format_units(raw, decimals):
    return f"{raw / (10**decimals):,.{decimals}f}"


def _button(label, url, background, text="white"):
    style = f"{BUTTON_STYLE} background-color: {background}; color: {text};"
    if url:
        return format_html('<a href="{}" style="{}">{}</a>', url, style, label)
    return format_html('<span style="{}">{}</span>', style, label)


def action_buttons(items):
    if not items:
        return "-"
    return format_html_join(" ", "{}", ((_button(*item),) for item in items))


class MintForm(forms.Form):

    recipient_address = forms.CharField(
        max_length=42,
        label="Recipient Address",
        help_text="Ethereum wallet address (0x...)",
        widget=forms.TextInput(attrs={"style": "width: 100%; font-family: monospace;"}),
    )
    recipient_name = forms.CharField(
        max_length=200,
        label="Recipient Name",
        help_text="Name of the recipient (for audit trail)",
    )
    amount = forms.DecimalField()
    deposit_reference = forms.CharField(
        max_length=100,
        label="Deposit Reference",
        help_text="Bank reference, transaction ID or synthetic scenario reference",
    )
    deposit_date = forms.DateField(
        label="Deposit Date",
        help_text="Date the deposit was received or assigned to the scenario",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Notes (Optional)",
    )

    def __init__(self, *args, decimals, symbol, **kwargs):
        super().__init__(*args, **kwargs)
        self.decimals = decimals
        unit = Decimal(1).scaleb(-decimals)
        self.fields["amount"] = forms.DecimalField(
            max_digits=18,
            decimal_places=decimals,
            min_value=unit,
            label=f"Amount ({symbol})",
            help_text=f"Token amount, e.g. {Decimal(100).quantize(unit)}; stored as raw units",
        )

    def clean_recipient_address(self):
        address = self.cleaned_data["recipient_address"]
        if not address.startswith("0x") or len(address) != 42:
            raise forms.ValidationError("Invalid Ethereum address format. Must be 42 characters starting with 0x.")
        return address

    def clean_amount(self):
        return int(self.cleaned_data["amount"].scaleb(self.decimals))
