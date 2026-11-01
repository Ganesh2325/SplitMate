"""Shared choices that models and services both need."""

GROUP_TYPES = [
    ("home", "Home"),
    ("trip", "Trip"),
    ("college", "College"),
    ("family", "Family"),
    ("office", "Office"),
    ("event", "Event"),
    ("other", "Other"),
]

SPLIT_METHODS = [
    ("equal", "Equal"),
    ("exact", "Exact amounts"),
    ("percent", "Percentage"),
    ("shares", "Shares"),
    ("itemized", "Itemized"),
]

GROUP_ROLES = [
    ("owner", "Owner"),
    ("admin", "Admin"),
    ("member", "Member"),
    ("viewer", "Read-only"),
]

MEMBERSHIP_STATUSES = [
    ("active", "Active"),
    ("left", "Left"),
    ("removed", "Removed"),
]

FREQUENCIES = [
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("fortnightly", "Fortnightly"),
    ("monthly", "Monthly"),
    ("quarterly", "Quarterly"),
    ("yearly", "Yearly"),
]

PAYMENT_METHODS = [
    ("cash", "Cash"),
    ("upi", "UPI"),
    ("bank", "Bank transfer"),
    ("paytm", "Paytm"),
    ("other", "Other"),
]

CURRENCIES = {
    "INR": {"code": "INR", "name": "Indian Rupee", "symbol": "₹", "decimals": 2},
    "USD": {"code": "USD", "name": "US Dollar", "symbol": "$", "decimals": 2},
    "EUR": {"code": "EUR", "name": "Euro", "symbol": "€", "decimals": 2},
    "GBP": {"code": "GBP", "name": "British Pound", "symbol": "£", "decimals": 2},
}

CURRENCY_CHOICES = [(code, f"{spec['name']} ({code})") for code, spec in CURRENCIES.items()]

LANGUAGE_CHOICES = [("en", "English")]

THEME_CHOICES = [
    ("system", "Match device"),
    ("light", "Light"),
    ("dark", "Dark"),
]

ADJUSTMENT_METHODS = [
    ("proportional", "Proportional to items"),
    ("equal", "Equal among people on the items"),
]
