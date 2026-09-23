def round_currency(amount):
    """Round amount to 2 decimal places using standard rounding."""
    return round(amount, 2)


def format_currency(amount, currency="USD"):
    rounded = round_currency(amount)
    return f"{currency} {rounded:.2f}"


def clamp(value, low, high):
    return max(low, min(value, high))
