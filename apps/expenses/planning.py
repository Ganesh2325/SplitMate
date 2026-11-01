"""Turn form input into payer amounts and participant shares."""

import re
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.common.allocations import split_by_shares, split_equal, split_exact, split_itemized, split_percentage
from apps.common.exceptions import AuthorizationError, DomainError
from apps.common.money import quantize_amount
from apps.friends.services import friend_ids
from apps.groups.access import can_add_expense
from apps.groups.models import GroupMembership


@dataclass
class SplitPlan:
    amount: Decimal
    currency: str
    payers: dict
    shares: dict
    items: list = field(default_factory=list)
    percentages: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)


def normalize_tags(raw_tags):
    names = []
    for part in raw_tags:
        for piece in str(part).split(","):
            name = piece.strip().lower()
            if not name:
                continue
            if not re.fullmatch(r"[a-z0-9][a-z0-9 \-]{0,29}", name):
                raise DomainError(
                    "Tags use letters, numbers, spaces, and hyphens, up to 30 characters.",
                    field="tags",
                )
            names.append(name)
    unique = list(dict.fromkeys(names))
    if len(unique) > 10:
        raise DomainError("Use at most 10 tags.", field="tags")
    return unique


def assert_people(actor, user_ids, group):
    user_ids = list(dict.fromkeys(user_ids))
    if not user_ids:
        raise DomainError("Choose at least one person.", field="participants")
    found = User.objects.filter(pk__in=user_ids, is_active=True, anonymized_at__isnull=True)
    if found.count() != len(user_ids):
        raise DomainError("One of the selected people is not available.", field="participants")
    if group is not None:
        if group.is_archived:
            raise DomainError("This group is archived.")
        membership = GroupMembership.objects.filter(
            group=group, user=actor, status=GroupMembership.Status.ACTIVE
        ).first()
        if not can_add_expense(membership):
            raise AuthorizationError("You cannot add expenses in this group.")
        member_ids = set(
            GroupMembership.objects.filter(
                group=group, status=GroupMembership.Status.ACTIVE, user_id__in=user_ids
            ).values_list("user_id", flat=True)
        )
        if set(user_ids) - member_ids:
            raise DomainError("Everyone on a group expense must be a group member.", field="participants")
    else:
        allowed = set(friend_ids(actor)) | {actor.id}
        if set(user_ids) - allowed:
            raise DomainError("Outside a group, choose yourself or a friend.", field="participants")
    return user_ids


def plan_split(
    *,
    actor,
    amount,
    currency,
    split_method,
    participant_ids,
    payers,
    group=None,
    exact=None,
    percentages=None,
    weights=None,
    items=None,
    tax=0,
    discount=0,
    tip=0,
    adjustment_method="proportional",
    expense_date=None,
    editing=False,
):
    amount = quantize_amount(amount, currency)
    if group is not None and currency != group.currency:
        raise DomainError("This group keeps its books in one currency.", field="currency")
    if expense_date is not None:
        today = timezone.localdate()
        if expense_date > today + timedelta(days=366):
            raise DomainError("That date is too far in the future.", field="expense_date")
    payer_map = {}
    for user_id, raw_amount in (payers or {}).items():
        if raw_amount in (None, ""):
            continue
        payer_map[int(user_id)] = quantize_amount(raw_amount, currency)
    if not payer_map:
        raise DomainError("Choose who paid.", field="payers")
    if len(payer_map) == 1 and sum(payer_map.values(), Decimal("0")) != amount:
        only_id, only_amount = next(iter(payer_map.items()))
        if only_amount != amount:
            raise DomainError("The payer's amount must equal the expense total.", field="payers")
    if sum(payer_map.values(), Decimal("0")) != amount:
        raise DomainError("Payments must add up to the expense total.", field="payers")

    people = list(dict.fromkeys(int(value) for value in participant_ids))
    normalized_items = []
    stored_percentages = {}
    stored_weights = {}
    if split_method == "equal":
        shares = split_equal(amount, people, currency)
    elif split_method == "exact":
        exact_map = {int(key): value for key, value in (exact or {}).items() if int(key) in people}
        shares = split_exact(amount, exact_map, currency)
    elif split_method == "percent":
        stored_percentages = {
            int(key): value for key, value in (percentages or {}).items() if int(key) in people
        }
        shares = split_percentage(amount, stored_percentages, currency)
    elif split_method == "shares":
        stored_weights = {int(key): value for key, value in (weights or {}).items() if int(key) in people}
        shares = split_by_shares(amount, stored_weights, currency)
    elif split_method == "itemized":
        shares, normalized_items = split_itemized(
            amount,
            items or [],
            currency,
            tax=tax,
            discount=discount,
            tip=tip,
            adjustment_method=adjustment_method,
        )
        people = list(shares)
    else:
        raise DomainError("Choose a split method.", field="split_method")

    if sum(shares.values(), Decimal("0")) != amount:
        raise DomainError("Shares must add up to the expense total.", field="participants")
    if any(value < 0 for value in shares.values()):
        raise DomainError("Shares cannot be negative.", field="participants")
    involved = set(people) | set(payer_map)
    if group is None and actor.id not in involved:
        raise DomainError("Include yourself on an expense that is not in a group.", field="participants")
    assert_people(actor, list(involved), group)
    return SplitPlan(
        amount=amount,
        currency=currency,
        payers=payer_map,
        shares=shares,
        items=normalized_items,
        percentages={key: value for key, value in stored_percentages.items()},
        weights={key: value for key, value in stored_weights.items()},
    )
