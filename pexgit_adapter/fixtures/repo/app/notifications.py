from app.utils import format_currency


def send_receipt(customer_email, amount, currency="USD"):
    """Placeholder for the real email/SMS integration."""
    return f"Receipt sent to {customer_email} for {format_currency(amount, currency)}"
