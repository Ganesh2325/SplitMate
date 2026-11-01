import calendar
from datetime import timedelta

from apps.recurring.models import RecurringExpense


def add_months(value, months, anchor_day):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor_day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def next_date(current, frequency, anchor_day):
    if frequency == RecurringExpense.frequency.field.choices[0][0] or frequency == "daily":
        return current + timedelta(days=1)
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "fortnightly":
        return current + timedelta(days=14)
    if frequency == "monthly":
        return add_months(current, 1, anchor_day)
    if frequency == "quarterly":
        return add_months(current, 3, anchor_day)
    if frequency == "yearly":
        return add_months(current, 12, anchor_day)
    raise ValueError(frequency)
