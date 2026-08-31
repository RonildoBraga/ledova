"""
Request utility functions for extracting metadata and information from Django requests.
"""


def extract_request_metadata(request):
    """
    Extract device and network metadata from a Django request object.

    Args:
        request: Django HttpRequest object

    Returns:
        tuple: (device_info, ip_address, user_agent)
            - device_info: dict containing host, origin, referer
            - ip_address: str client IP address
            - user_agent: str client user agent string
    """
    device_info = {}
    ip_address = None
    user_agent = None

    if request:
        # Extract IP address, considering proxy headers
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR")

        # Extract user agent
        user_agent = request.META.get("HTTP_USER_AGENT")

        # Extract device/client information
        device_info = {
            "host": request.META.get("HTTP_HOST"),
            "origin": request.META.get("HTTP_ORIGIN"),
            "referer": request.META.get("HTTP_REFERER"),
        }

    return device_info, ip_address, user_agent


def get_client_ip(request):
    """
    Extract the client IP address from a Django request.

    Args:
        request: Django HttpRequest object

    Returns:
        str: Client IP address
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
