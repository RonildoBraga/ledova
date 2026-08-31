from .client import twilio_integration


def send_sms(to_number, message):
    """
    Utility function to send SMS using Twilio integration

    Args:
        to_number (str): The recipient's phone number
        message (str): The message content

    Returns:
        dict: Response from Twilio API
    """
    return twilio_integration.send_sms(to_number, message)
