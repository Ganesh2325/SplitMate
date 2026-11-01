"""Greedy debt simplification.

The same nets always produce the same payments. This does not claim to find
the smallest possible number of payments in every graph.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.common.exceptions import DomainError
from apps.common.money import from_minor, to_minor


@dataclass(frozen=True)
class Suggestion:
    debtor_id: int
    creditor_id: int
    amount: Decimal
    currency: str
    group_id: int | None = None


def simplify_nets(nets: dict, currency: str, group_id=None) -> list[Suggestion]:
    minor = {}
    for user_id, amount in nets.items():
        value = to_minor(Decimal(amount), currency)
        if value:
            minor[user_id] = value
    if not minor:
        return []
    if sum(minor.values()) != 0:
        raise DomainError("These balances do not add up to zero, so they cannot be simplified.")
    creditors = sorted(
        [(user_id, value) for user_id, value in minor.items() if value > 0],
        key=lambda item: (-item[1], item[0]),
    )
    debtors = sorted(
        [(user_id, -value) for user_id, value in minor.items() if value < 0],
        key=lambda item: (-item[1], item[0]),
    )
    creditors = [list(item) for item in creditors]
    debtors = [list(item) for item in debtors]
    debtor_index = 0
    creditor_index = 0
    suggestions = []
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        pay = min(debtors[debtor_index][1], creditors[creditor_index][1])
        if pay:
            suggestions.append(
                Suggestion(
                    debtor_id=debtors[debtor_index][0],
                    creditor_id=creditors[creditor_index][0],
                    amount=from_minor(pay, currency),
                    currency=currency,
                    group_id=group_id,
                )
            )
        debtors[debtor_index][1] -= pay
        creditors[creditor_index][1] -= pay
        if debtors[debtor_index][1] == 0:
            debtor_index += 1
        if creditors[creditor_index][1] == 0:
            creditor_index += 1
    return suggestions


def suggestions_match_nets(nets: dict, suggestions, currency: str) -> bool:
    rebuilt = {user_id: Decimal("0") for user_id in nets}
    for suggestion in suggestions:
        rebuilt[suggestion.debtor_id] = rebuilt.get(suggestion.debtor_id, Decimal("0")) - suggestion.amount
        rebuilt[suggestion.creditor_id] = rebuilt.get(suggestion.creditor_id, Decimal("0")) + suggestion.amount
    for user_id, net in nets.items():
        if to_minor(rebuilt.get(user_id, Decimal("0")), currency) != to_minor(Decimal(net), currency):
            return False
    return True
