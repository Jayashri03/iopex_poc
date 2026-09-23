from app.utils import round_currency


def calculate_total(price, quantity):
    return round_currency(price * quantity)


def apply_discount(total, discount_percent):
    """Apply a percentage discount to a total."""
    if discount_percent < 0:
        raise ValueError("discount_percent cannot be negative")
    discounted = total * (1 - discount_percent / 100)
    return round_currency(discounted)
