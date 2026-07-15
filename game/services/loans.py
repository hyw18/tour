class LoanService:
    def __init__(self, engine):
        self.engine = engine

    def deposit(self, player, amount, source, *, taxable=True, region_id=None, building_type=None, building_id=None, record=True):
        amount = int(amount)
        if amount < 0:
            raise ValueError("deposit amount cannot be negative")
        if record:
            self.engine._add_income(player, amount, source, region_id, taxable, building_type, building_id)
        player.cash_won += amount
        payment = self.engine._auto_repay_loan(player, amount)
        if payment:
            self.engine._ledger(player)["loan_payment"] += payment
        return {"amount_won": amount, "loan_payment_won": payment, "cash_retained_won": amount - payment}

    def is_mature(self, player, loan):
        return self.engine.state.lap_numbers.get(player.id, 0) >= loan["due_lap"]
