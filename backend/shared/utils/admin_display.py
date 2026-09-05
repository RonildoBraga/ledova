from django.utils.html import format_html, format_html_join

BUTTON_STYLE = (
    "display: inline-block; padding: 6px 12px; margin: 2px; "
    "text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;"
)


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
