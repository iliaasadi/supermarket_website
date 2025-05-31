from suds.client import Client
from flask import url_for, current_app
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ZARINPAL_WEBSERVICE = 'https://www.zarinpal.com/pg/services/WebGate/wsdl'
MMERCHANT_ID = '12396216-4ec9-40fc-935f-f98fdfdf2f73'  # Your provided merchant ID

def create_payment_request(amount, description, email, callback_url):
    """
    Create a payment request with ZarinPal
    Returns: (status, authority) tuple
    """
    try:
        client = Client(ZARINPAL_WEBSERVICE)
        result = client.service.PaymentRequest(
            MMERCHANT_ID,
            amount,
            description,
            email,
            '',
            callback_url
        )
        logger.info(f"Payment request status: {result.Status}, authority: {result.Authority}")
        return result.Status, result.Authority
    except Exception as e:
        logger.error(f"Error creating payment request: {str(e)}")
        return None, None

def verify_payment(amount, authority):
    """
    Verify a payment with ZarinPal
    Returns: (ref_id, status) tuple
    """
    try:
        client = Client(ZARINPAL_WEBSERVICE)
        result = client.service.PaymentVerification(
            MMERCHANT_ID,
            authority,
            amount
        )
        logger.info(f"Payment verification status: {result.Status}, ref_id: {result.RefID}")
        return result.RefID, result.Status
    except Exception as e:
        logger.error(f"Error verifying payment: {str(e)}")
        return None, None 