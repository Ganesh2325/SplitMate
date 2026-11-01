"""Deterministic money allocation.

Shares, percentages, weights, and payer obligations are calculated in minor
units so the parts always add back to the original total.
"""

from decimal import Decimal, ROUND_HALF_UP

from apps.common.exceptions import DomainError
from apps.common.money import from_minor, quantize_amount, to_minor


def allocate_by_weights(total: Decimal, weights: dict, currency: str) -> dict:
    """Split ``total`` across keys in proportion to positive weights.

    Ties in the remainder are broken by sorting the key, so the same input
    always produces the same shares. The returned values sum to ``total``.
    """
    if not weights:
        raise DomainError("Choose at least one person.")
    total_minor = to_minor(total, currency)
    cleaned = []
    for key, weight in weights.items():
        number = Decimal(weight)
        if number < 0:
            raise DomainError("Shares and percentages cannot be negative.")
        cleaned.append((key, number))
    weight_sum = sum((weight for _, weight in cleaned), Decimal("0"))
    if weight_sum <= 0:
        raise DomainError("Enter a positive share, percentage, or weight.")
    if total_minor == 0:
        return {key: from_minor(0, currency) for key, _ in cleaned}

    bases = {}
    fractions = []
    assigned = 0
    for key, weight in cleaned:
        exact = Decimal(total_minor) * weight / weight_sum
        base = int(exact)
        bases[key] = base
        assigned += base
        fractions.append((exact - Decimal(base), key))
    remainder = total_minor - assigned
    fractions.sort(key=lambda item: (-item[0], str(item[1])))
    for index in range(remainder):
        _, key = fractions[index]
        bases[key] += 1
    if sum(bases.values()) != total_minor:
        raise DomainError("Could not allocate this amount exactly.")
    return {key: from_minor(amount, currency) for key, amount in bases.items()}


def apportion_matrix(row_totals: dict, col_totals: dict) -> dict:
    """Return minor-unit cells whose row and column sums match the margins."""
    if sum(row_totals.values()) != sum(col_totals.values()):
        raise DomainError("Payments and shares are not balanced.")
    total = sum(row_totals.values())
    rows = list(row_totals)
    cols = list(col_totals)
    cells = {(row, col): 0 for row in rows for col in cols}
    if total == 0:
        return cells
    fractions = []
    for row in rows:
        for col in cols:
            exact = Decimal(row_totals[row]) * Decimal(col_totals[col]) / Decimal(total)
            base = int(exact)
            cells[(row, col)] = base
            fractions.append((exact - Decimal(base), row, col))
    row_left = {
        row: row_totals[row] - sum(cells[(row, col)] for col in cols) for row in rows
    }
    col_left = {
        col: col_totals[col] - sum(cells[(row, col)] for row in rows) for col in cols
    }
    fractions.sort(key=lambda item: (-item[0], str(item[1]), str(item[2])))
    for _, row, col in fractions:
        if row_left[row] > 0 and col_left[col] > 0:
            cells[(row, col)] += 1
            row_left[row] -= 1
            col_left[col] -= 1
    for row in sorted(rows, key=str):
        for col in sorted(cols, key=str):
            while row_left[row] > 0 and col_left[col] > 0:
                cells[(row, col)] += 1
                row_left[row] -= 1
                col_left[col] -= 1
    if any(row_left.values()) or any(col_left.values()):
        raise DomainError("Could not allocate this expense exactly.")
    return cells


def net_directions(directed: dict) -> dict:
    """Collapse opposite debts between the same pair.

    Negative amounts are treated as the opposite direction so settlement
    adjustments can be mixed with expense obligations.
    """
    pairs = {}
    for (debtor, creditor), amount in directed.items():
        amount = Decimal(amount)
        if amount == 0 or debtor == creditor:
            continue
        if amount < 0:
            debtor, creditor, amount = creditor, debtor, -amount
        if debtor <= creditor:
            low, high, sign = debtor, creditor, Decimal("1")
        else:
            low, high, sign = creditor, debtor, Decimal("-1")
        pairs[(low, high)] = pairs.get((low, high), Decimal("0")) + (sign * amount)
    result = {}
    for (low, high), amount in pairs.items():
        if amount > 0:
            result[(low, high)] = amount
        elif amount < 0:
            result[(high, low)] = -amount
    return result


def obligations_from_parts(payers: dict, shares: dict, currency: str) -> dict:
    """Map (debtor_id, creditor_id) to the amount the debtor owes the creditor.

    Diagonal self-funding is removed. Opposite directions are netted.
    The caller can reconstruct each person's paid-minus-share net from these
    pairs.
    """
    users = set(payers) | set(shares)
    row_totals = {user: to_minor(shares.get(user, Decimal("0")), currency) for user in users}
    col_totals = {user: to_minor(payers.get(user, Decimal("0")), currency) for user in users}
    active = [user for user in users if row_totals[user] or col_totals[user]]
    row_totals = {user: row_totals[user] for user in active}
    col_totals = {user: col_totals[user] for user in active}
    if sum(row_totals.values()) == 0:
        return {}
    cells = apportion_matrix(row_totals, col_totals)
    directed = {}
    for (debtor, creditor), minor in cells.items():
        if debtor == creditor or minor <= 0:
            continue
        directed[(debtor, creditor)] = from_minor(minor, currency)
    return net_directions(directed)


def pair_effect(obligations: dict, user_id: int, other_id: int) -> Decimal:
    """Positive when ``other_id`` owes ``user_id``."""
    effect = obligations.get((other_id, user_id), Decimal("0"))
    effect -= obligations.get((user_id, other_id), Decimal("0"))
    return effect


def split_equal(total: Decimal, user_ids, currency: str) -> dict:
    ids = list(dict.fromkeys(user_ids))
    if not ids:
        raise DomainError("Choose at least one person.", field="participants")
    return allocate_by_weights(total, {user_id: Decimal("1") for user_id in ids}, currency)


def split_exact(total: Decimal, amounts: dict, currency: str) -> dict:
    if not amounts:
        raise DomainError("Enter an amount for each person.", field="participants")
    cleaned = {
        user_id: quantize_amount(amount, currency, allow_zero=True)
        for user_id, amount in amounts.items()
    }
    if sum(cleaned.values(), Decimal("0")) != total:
        raise DomainError("Exact shares must add up to the expense total.", field="participants")
    return cleaned


def _parse_percent(value) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except Exception as exc:
        raise DomainError("Enter a valid percentage.", field="participants") from exc
    rounded = amount.quantize(Decimal("0.01"))
    if rounded != amount:
        raise DomainError("Percentages support at most 2 decimal places.", field="participants")
    if rounded < 0:
        raise DomainError("Percentage cannot be negative.", field="participants")
    return rounded


def split_percentage(total: Decimal, percentages: dict, currency: str) -> dict:
    if not percentages:
        raise DomainError("Enter a percentage for each person.", field="participants")
    cleaned = {user_id: _parse_percent(value) for user_id, value in percentages.items()}
    if sum(cleaned.values(), Decimal("0")) != Decimal("100"):
        raise DomainError("Percentages must add up to 100.", field="participants")
    if all(value == 0 for value in cleaned.values()):
        raise DomainError("Enter a percentage for at least one person.", field="participants")
    return allocate_by_weights(total, cleaned, currency)


def split_by_shares(total: Decimal, weights: dict, currency: str) -> dict:
    if not weights:
        raise DomainError("Enter a share weight for each person.", field="participants")
    cleaned = {}
    for user_id, weight in weights.items():
        number = quantize_amount(weight, currency, allow_zero=False)
        cleaned[user_id] = number
    return allocate_by_weights(total, cleaned, currency)


def split_itemized(
    total,
    items,
    currency,
    *,
    tax=Decimal("0"),
    discount=Decimal("0"),
    tip=Decimal("0"),
    adjustment_method="proportional",
):
    """Allocate itemized lines, then tax, tip, and discount.

    ``items`` is a list of dicts: description, quantity, unit_price, participant_ids.
    Returns ``(shares, normalized_items)``. Line totals use currency precision.
    """
    from apps.common.money import quantum

    if not items:
        raise DomainError("Add at least one item.", field="items")
    if adjustment_method not in {"proportional", "equal"}:
        raise DomainError("Choose how tax, tip, and discount are split.", field="adjustment_method")
    tax = quantize_amount(tax or 0, currency, allow_zero=True)
    discount = quantize_amount(discount or 0, currency, allow_zero=True)
    tip = quantize_amount(tip or 0, currency, allow_zero=True)

    normalized = []
    subtotals = {}
    for item in items:
        description = (item.get("description") or "").strip()
        if not description:
            raise DomainError("Each item needs a description.", field="items")
        quantity = quantize_amount(item["quantity"], currency, allow_zero=False)
        unit_price = quantize_amount(item["unit_price"], currency, allow_zero=False)
        line_total = (quantity * unit_price).quantize(quantum(currency), rounding=ROUND_HALF_UP)
        if line_total <= 0:
            raise DomainError(f"“{description}” needs a total greater than zero.", field="items")
        people = list(dict.fromkeys(item["participant_ids"]))
        if not people:
            raise DomainError(f"Choose who shared “{description}”.", field="items")
        line_shares = split_equal(line_total, people, currency)
        for user_id, amount in line_shares.items():
            subtotals[user_id] = subtotals.get(user_id, Decimal("0")) + amount
        normalized.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
                "shares": line_shares,
            }
        )

    subtotal = sum((item["line_total"] for item in normalized), Decimal("0"))
    return _apply_adjustments(
        total=total,
        subtotal=subtotal,
        subtotals=subtotals,
        normalized=normalized,
        currency=currency,
        adjustment_method=adjustment_method,
        tax=tax,
        discount=discount,
        tip=tip,
    )


def _apply_adjustments(total, subtotal, subtotals, normalized, currency, adjustment_method, tax, discount, tip):
    grand = subtotal + tax + tip - discount
    if grand != total:
        raise DomainError(
            f"Items, tax, tip, and discount come to {grand}, but the expense total is {total}.",
            field="amount",
        )
    if grand <= 0:
        raise DomainError("The expense total must be greater than zero.", field="amount")
    weights = dict(subtotals)
    if adjustment_method == "equal":
        weights = {user_id: Decimal("1") for user_id in subtotals}
    final = dict(subtotals)
    if tax:
        for user_id, amount in allocate_by_weights(tax, weights, currency).items():
            final[user_id] = final.get(user_id, Decimal("0")) + amount
    if tip:
        for user_id, amount in allocate_by_weights(tip, weights, currency).items():
            final[user_id] = final.get(user_id, Decimal("0")) + amount
    if discount:
        for user_id, amount in allocate_by_weights(discount, weights, currency).items():
            final[user_id] = final.get(user_id, Decimal("0")) - amount
            if final[user_id] < 0:
                raise DomainError("The discount is larger than someone's items.", field="discount")
    if sum(final.values(), Decimal("0")) != total:
        raise DomainError("Item shares do not add up to the expense total.", field="items")
    return final, normalized
