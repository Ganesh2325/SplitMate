from decimal import Decimal

from django import template

from apps.common.money import format_money

register = template.Library()


@register.filter
def money(value, currency="INR"):
    if value is None or value == "":
        return ""
    return format_money(value, currency or "INR")


@register.filter
def abs_value(value):
    return abs(value or 0)


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return ""
    return mapping.get(key, mapping.get(str(key), ""))


@register.filter
def display_name(person):
    if person is None or person == "":
        return ""
    return getattr(person, "display_name", str(person))


@register.simple_tag
def balance_phrase(amount):
    amount = Decimal(amount or 0)
    if amount > 0:
        return "Owes you"
    if amount < 0:
        return "You owe"
    return "Settled"
