from app.payments import apply_discount, calculate_total


class Order:
    def __init__(self, order_id, items, customer_email):
        self.order_id = order_id
        self.items = items
        self.customer_email = customer_email

    def subtotal(self):
        total = 0
        for item in self.items:
            total += calculate_total(item["price"], item["quantity"])
        return round(total, 2)

    def total_with_discount(self, discount_percent):
        return apply_discount(self.subtotal(), discount_percent)
