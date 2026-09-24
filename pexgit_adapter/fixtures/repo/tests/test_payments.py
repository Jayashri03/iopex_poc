from app.payments import apply_discount, calculate_total


def test_calculate_total():
    assert calculate_total(10, 3) == 30.0


def test_apply_discount_basic():
    assert apply_discount(100, 10) == 90.0


def test_apply_discount_rejects_negative():
    try:
        apply_discount(100, -5)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for negative discount")
