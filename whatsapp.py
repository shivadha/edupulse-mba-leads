"""
EduPulse India — WhatsApp notification via Twilio / Meta Cloud API
Sends WhatsApp messages to new leads (free tier via Twilio sandbox or Meta).
Falls back gracefully if no credentials are configured.
"""

import urllib.request
import urllib.parse
import json
import os
import logging

logger = logging.getLogger("edupulse.whatsapp")

# Configure in .env or environment variables
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox
ADMIN_WHATSAPP = os.getenv("ADMIN_WHATSAPP_NUMBER", "")  # e.g. +919876543210

# Meta Cloud API (alternative)
META_TOKEN = os.getenv("META_WHATSAPP_TOKEN", "")
META_PHONE_ID = os.getenv("META_PHONE_NUMBER_ID", "")


def send_lead_whatsapp(lead: dict) -> bool:
    """
    Send WhatsApp notification about a new lead.
    Tries Twilio first, then Meta Cloud API, then logs-only as fallback.
    """
    name = lead.get("name", "")
    phone = lead.get("phone", "")
    exam = lead.get("target_exam", "")
    city = lead.get("city", "")
    year = lead.get("target_year", "")

    message = (
        f"🎓 *New EduPulse Lead!*\n\n"
        f"👤 Name: {name}\n"
        f"📱 Phone: {phone}\n"
        f"🏙️ City: {city}\n"
        f"📚 Target: {exam} {year}\n\n"
        f"📊 Check dashboard: http://localhost:5050/admin"
    )

    # Try Twilio
    if TWILIO_SID and TWILIO_TOKEN and ADMIN_WHATSAPP:
        try:
            return _send_twilio(message, ADMIN_WHATSAPP)
        except Exception as e:
            logger.warning("Twilio failed: %s", e)

    # Try Meta Cloud API
    if META_TOKEN and META_PHONE_ID and ADMIN_WHATSAPP:
        try:
            return _send_meta(message, ADMIN_WHATSAPP)
        except Exception as e:
            logger.warning("Meta WhatsApp failed: %s", e)

    # Fallback: just log
    logger.info("[WhatsApp MOCK] Would send to %s: %s", ADMIN_WHATSAPP or "ADMIN", message)
    return True  # Don't block lead saving


def _send_twilio(message: str, to_number: str) -> bool:
    """Send via Twilio's REST API."""
    import base64
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    data = urllib.parse.urlencode({
        "From": TWILIO_FROM,
        "To": f"whatsapp:{to_number}",
        "Body": message,
    }).encode()
    credentials = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {credentials}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        logger.info("Twilio sent: %s", result.get("sid"))
        return True


def _send_meta(message: str, to_number: str) -> bool:
    """Send via Meta Cloud WhatsApp API."""
    url = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": to_number.replace("+", ""),
        "type": "text",
        "text": {"body": message}
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {META_TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        logger.info("Meta WhatsApp sent: %s", result)
        return True
