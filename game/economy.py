from decimal import Decimal, ROUND_HALF_UP


WON_ROUNDING_UNIT = 50_000


def to_won(value):
    if not isinstance(value, int):
        raise TypeError("money values must be stored as integer won")
    return value


def apply_rate(amount_won, numerator, denominator=100):
    amount = Decimal(to_won(amount_won)) * Decimal(numerator) / Decimal(denominator)
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def apply_rate_rounded_50k(amount_won, numerator, denominator=100):
    return round_to_50k(apply_rate(amount_won, numerator, denominator))


def round_to_50k(amount_won):
    amount = Decimal(to_won(amount_won))
    unit = Decimal(WON_ROUNDING_UNIT)
    return int((amount / unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit)
