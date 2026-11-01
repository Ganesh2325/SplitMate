"""Currency-aware decimal helpers. Money never uses binary floats."""

from decimal import Decimal, ROUND_HALF_UP

from apps.common.constants import CURRENCIES
from apps.common.exceptions import DomainError


def decimals_for(currency: str) -> int:
    try:
        return CURRENCIES[currency]["decimals"]
    except KeyError as exc:
        raise DomainError("Choose a supported currency.", field="currency") from exc


def quantum(currency: str) -> Decimal:
    return Decimal("1").scaleb(-decimals_for(currency))


def quantize_amount(value, currency: str, *, allow_zero=False) -> Decimal:
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value).strip())
        except Exception as exc:
            raise DomainError("Enter a valid amount.") from exc
    if not amount.is_finite():
        raise DomainError("Enter a valid amount.")
    rounded = amount.quantize(quantum(currency), rounding=ROUND_HALF_UP)
    if rounded != amount:
        places = decimals_for(currency)
        raise DomainError(f"Use at most {places} decimal places.")
    if allow_zero:
        if rounded < 0:
            raise DomainError("Amount cannot be negative.")
    elif rounded <= 0:
        raise DomainError("Amount must be greater than zero.")
    if rounded > Decimal("9999999999.99"):
        raise DomainError("Amount is too large.")
    return rounded


def to_minor(value: Decimal, currency: str) -> int:
    scale = Decimal(10) ** decimals_for(currency)
    return int((Decimal(value) * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor(value: int, currency: str) -> Decimal:
    scale = Decimal(10) ** decimals_for(currency)
    return (Decimal(int(value)) / scale).quantize(quantum(currency))


def format_money(value, currency="INR") -> str:
    spec = CURRENCIES.get(currency, {"symbol": "", "decimals": 2})
    places = spec["decimals"]
    amount = Decimal(value).quantize(Decimal("1").scaleb(-places))
    sign = "-" if amount < 0 else ""
    formatted = f"{abs(amount):,.{places}f}"
    return f"{sign}{spec['symbol']}{formatted}"


def money_sort_key(value: Decimal) -> int:
    return to_minor(value, "INR")
