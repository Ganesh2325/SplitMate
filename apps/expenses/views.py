import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.common.exceptions import AuthorizationError, DomainError
from apps.expenses.access import can_edit_expense, can_view_expense
from apps.expenses.discussion import add_comment, edit_comment, hide_comment
from apps.expenses.models import Expense, ExpenseAttachment, ExpenseComment, ExpenseTemplate, SavedSplitPreference
from apps.expenses.receipts import delete_receipt, scan_receipt, store_receipt
from apps.expenses.selectors import categories_for, filter_expenses
from apps.expenses.services import category_or_error, create_expense, update_expense, void_expense
from apps.friends.services import friend_ids
from apps.groups.access import active_membership
from apps.groups.models import Group, GroupMembership


def _expense_or_404(user, pk):
    expense = get_object_or_404(
        Expense.objects.select_related("category", "group", "created_by").prefetch_related(
            "payers__user", "shares__user", "items__assignments__user", "tag_assignments__tag", "attachments", "revisions__actor"
        ),
        pk=pk,
    )
    if not can_view_expense(user, expense):
        raise Http404()
    return expense


def _group_from_request(user, raw):
    if not raw:
        return None
    group = get_object_or_404(Group, pk=raw)
    if not active_membership(user, group):
        raise Http404()
    return group


def _candidates(user, group):
    if group is not None:
        ids = GroupMembership.objects.filter(group=group, status=GroupMembership.Status.ACTIVE).values_list(
            "user_id", flat=True
        )
    else:
        ids = set(friend_ids(user)) | {user.id}
    return list(User.objects.filter(pk__in=ids, is_active=True).order_by("first_name", "username"))


def _blank_draft(user):
    return {
        "participant_ids": {user.id},
        "payer_ids": {user.id},
        "payer_amounts": {},
        "exact": {},
        "percent": {},
        "weight": {},
        "items": [],
    }


def _grab(post, prefix, selected):
    found = {}
    for user_id in selected:
        raw = (post.get(f"{prefix}_{user_id}") or "").strip()
        if raw:
            found[user_id] = raw
    return found


def _draft_from_post(post):
    def ids(name):
        return {int(value) for value in post.getlist(name) if str(value).isdigit()}

    participant_ids = ids("participant")
    payer_ids = ids("payer")
    items = []
    for index in range(40):
        description = (post.get(f"item_description_{index}") or "").strip()
        if not description:
            continue
        items.append(
            {
                "description": description,
                "quantity": post.get(f"item_quantity_{index}") or "",
                "unit_price": post.get(f"item_unit_price_{index}") or "",
                "participant_ids": [
                    int(value) for value in post.getlist(f"item_participants_{index}") if str(value).isdigit()
                ],
            }
        )
    return {
        "participant_ids": participant_ids,
        "payer_ids": payer_ids,
        "payer_amounts": _grab(post, "payer_amount", payer_ids),
        "exact": _grab(post, "exact", participant_ids),
        "percent": _grab(post, "percent", participant_ids),
        "weight": _grab(post, "weight", participant_ids),
        "items": items,
    }


def _draft_from_expense(expense):
    items = []
    for item in expense.items.all():
        items.append(
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "participant_ids": list(item.assignments.values_list("user_id", flat=True)),
            }
        )
    return {
        "participant_ids": set(expense.shares.values_list("user_id", flat=True)),
        "payer_ids": set(expense.payers.values_list("user_id", flat=True)),
        "payer_amounts": {row.user_id: row.amount for row in expense.payers.all()},
        "exact": {row.user_id: row.amount for row in expense.shares.all()},
        "percent": {row.user_id: row.percentage for row in expense.shares.all() if row.percentage is not None},
        "weight": {row.user_id: row.weight for row in expense.shares.all() if row.weight is not None},
        "items": items,
    }


def _lookup(draft, kind, user_id):
    source = draft.get(kind)
    if source is None:
        return ""
    if hasattr(source, "get") and not hasattr(source, "getlist"):
        value = source.get(user_id, "")
        return "" if value is None else value
    return source.get(f"{kind if kind != 'payer_amounts' else 'payer_amount'}_{user_id}", "")


@login_required
def expense_list(request):
    queryset = filter_expenses(request.user, request.GET)
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "expenses/list.html",
        {
            "page_obj": page,
            "expenses": page.object_list,
            "groups": Group.objects.filter(
                memberships__user=request.user, memberships__status=GroupMembership.Status.ACTIVE
            ),
            "categories": categories_for(request.user),
            "filters": request.GET,
        },
    )


def _save_payload(request, draft, candidates, group):
    participant_ids = list(draft["participant_ids"])
    payer_ids = list(draft["payer_ids"])
    payer_amounts = dict(draft["payer_amounts"])
    exact = draft["exact"]
    percent = draft["percent"]
    weight = draft["weight"]
    if len(payer_ids) == 1 and payer_ids[0] not in payer_amounts:
        payer_amounts[payer_ids[0]] = request.POST.get("amount") or "0"
    items = []
    for item in draft["items"]:
        items.append(
            {
                "description": item["description"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "participant_ids": item["participant_ids"],
            }
        )
    return {
        "description": request.POST.get("description", ""),
        "amount": request.POST.get("amount") or "0",
        "currency": group.currency if group else request.POST.get("currency") or request.user.preferred_currency,
        "expense_date": request.POST.get("expense_date"),
        "split_method": request.POST.get("split_method") or "equal",
        "participant_ids": participant_ids,
        "payers": payer_amounts,
        "exact": exact,
        "percentages": percent,
        "weights": weight,
        "items": items,
        "tax": request.POST.get("tax") or "0",
        "discount": request.POST.get("discount") or "0",
        "tip": request.POST.get("tip") or "0",
        "adjustment_method": request.POST.get("adjustment_method") or "proportional",
        "notes": request.POST.get("notes") or "",
        "tags": request.POST.get("tags") or "",
        "category_id": request.POST.get("category"),
    }


@login_required
def expense_form(request, pk=None):
    expense = _expense_or_404(request.user, pk) if pk else None
    if expense and not can_edit_expense(request.user, expense):
        raise Http404()
    group = expense.group if expense else _group_from_request(request.user, request.POST.get("group") or request.GET.get("group"))
    seed = {}
    if request.method == "GET" and expense is None:
        source_id = request.session.pop("duplicate_expense", None)
        template_payload = request.session.pop("expense_template", None) or {}
        if source_id:
            try:
                expense_source = _expense_or_404(request.user, source_id)
                draft = _draft_from_expense(expense_source)
                group = expense_source.group
                seed = {
                    "description": expense_source.description,
                    "amount": expense_source.amount,
                    "notes": expense_source.notes,
                    "category": expense_source.category_id,
                    "expense_date": expense_source.expense_date.isoformat(),
                    "split_method": expense_source.split_method,
                    "tags": ", ".join(expense_source.tag_assignments.values_list("tag__name", flat=True)),
                }
            except Http404:
                draft = _blank_draft(request.user)
        else:
            draft = _blank_draft(request.user)
            seed = template_payload
        token = uuid.uuid4()
    elif request.method == "GET":
        draft = _draft_from_expense(expense)
        token = uuid.uuid4()
    else:
        draft = _draft_from_post(request.POST)
        token = request.POST.get("client_token") or uuid.uuid4()
    candidates = _candidates(request.user, group)
    error = None
    if request.method == "POST" and "refresh" not in request.POST:
        from datetime import datetime

        payload = _save_payload(request, draft, candidates, group)
        try:
            when = datetime.strptime(payload["expense_date"], "%Y-%m-%d").date()
            category = category_or_error(request.user, payload["category_id"], group)
            common = dict(
                actor=request.user,
                description=payload["description"],
                amount=payload["amount"],
                expense_date=when,
                split_method=payload["split_method"],
                participant_ids=payload["participant_ids"],
                payers=payload["payers"],
                category=category,
                notes=payload["notes"],
                tags=[payload["tags"]],
                exact=payload["exact"],
                percentages=payload["percentages"],
                weights=payload["weights"],
                items=payload["items"],
                tax=payload["tax"],
                discount=payload["discount"],
                tip=payload["tip"],
                adjustment_method=payload["adjustment_method"],
                request=request,
            )
            if expense is None:
                saved = create_expense(currency=payload["currency"], client_token=token, group=group, **common)
                upload = request.FILES.get("receipt")
                if upload:
                    store_receipt(saved, upload, request.user)
                messages.success(request, "Expense saved.")
            else:
                saved = update_expense(expense, currency=expense.currency, group=expense.group, reason=request.POST.get("reason", ""), **common)
                messages.success(request, "Expense updated.")
            return redirect("expenses:detail", pk=saved.pk)
        except (DomainError, AuthorizationError, ValueError) as exc:
            error = str(exc)
    groups = Group.objects.filter(
        memberships__user=request.user,
        memberships__status=GroupMembership.Status.ACTIVE,
        memberships__role__in=["owner", "admin", "member"],
        archived_at__isnull=True,
    )
    item_rows = list(draft["items"])
    while len(item_rows) < 4:
        item_rows.append({"description": "", "quantity": "", "unit_price": "", "participant_ids": []})
    return render(
        request,
        "expenses/form.html",
        {
            "expense": expense,
            "group": group,
            "groups": groups,
            "candidates": candidates,
            "draft": draft,
            "categories": categories_for(request.user, group),
            "token": token,
            "error": error,
            "posted": request.POST if request.method == "POST" else None,
            "item_rows": item_rows,
            "split_method": (request.POST.get("split_method") if request.method == "POST" else None)
            or (expense.split_method if expense else seed.get("split_method") or (group.default_split_method if group else "equal")),
            "currency": group.currency if group else request.user.preferred_currency,
            "seed": seed,
        },
    )


@login_required
def expense_detail(request, pk):
    expense = _expense_or_404(request.user, pk)
    comments = expense.comments.select_related("author").all()
    page = Paginator(comments, 20).get_page(request.GET.get("cpage"))
    return render(
        request,
        "expenses/detail.html",
        {"expense": expense, "comments": page, "can_edit": can_edit_expense(request.user, expense)},
    )


@login_required
def expense_duplicate(request, pk):
    expense = _expense_or_404(request.user, pk)
    request.session["duplicate_expense"] = expense.pk
    return redirect("expenses:add")


@login_required
@require_POST
def expense_void(request, pk):
    expense = _expense_or_404(request.user, pk)
    try:
        void_expense(expense, actor=request.user, reason=request.POST.get("reason", ""), request=request)
        messages.success(request, "Expense voided. The original record is still in the history.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("expenses:detail", pk=expense.pk)


@login_required
@require_POST
def expense_comment(request, pk):
    expense = _expense_or_404(request.user, pk)
    comment_id = request.POST.get("comment_id")
    try:
        if request.POST.get("action") == "hide" and comment_id:
            hide_comment(get_object_or_404(ExpenseComment, pk=comment_id, expense=expense), request.user, request)
        elif comment_id:
            edit_comment(
                get_object_or_404(ExpenseComment, pk=comment_id, expense=expense),
                request.user,
                request.POST.get("body", ""),
                request,
            )
        else:
            add_comment(expense, request.user, request.POST.get("body", ""), request)
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("expenses:detail", pk=expense.pk)


@login_required
@require_POST
def expense_receipt(request, pk):
    expense = _expense_or_404(request.user, pk)
    upload = request.FILES.get("receipt")
    if not upload:
        messages.error(request, "Choose a file.")
        return redirect("expenses:detail", pk=pk)
    try:
        store_receipt(expense, upload, request.user)
        messages.success(request, "Receipt added.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("expenses:detail", pk=pk)


@login_required
def receipt_download(request, pk):
    attachment = get_object_or_404(ExpenseAttachment.objects.select_related("expense"), pk=pk)
    if not can_view_expense(request.user, attachment.expense):
        raise Http404()
    disposition = "attachment" if request.GET.get("download") else "inline"
    response = FileResponse(attachment.file.open("rb"), as_attachment=disposition == "attachment", filename=attachment.original_name)
    response["Content-Type"] = attachment.content_type
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def receipt_delete(request, pk):
    attachment = get_object_or_404(ExpenseAttachment.objects.select_related("expense"), pk=pk)
    if not can_view_expense(request.user, attachment.expense):
        raise Http404()
    try:
        delete_receipt(attachment, request.user)
        messages.success(request, "Receipt removed.")
    except AuthorizationError as exc:
        messages.error(request, str(exc))
    return redirect("expenses:detail", pk=attachment.expense_id)


@login_required
@require_POST
def receipt_scan(request):
    upload = request.FILES.get("receipt")
    if not upload:
        return JsonResponse({"available": False, "message": "Choose a receipt first."})
    return JsonResponse(scan_receipt(upload))


@login_required
def template_list(request):
    templates = ExpenseTemplate.objects.filter(user=request.user).select_related("group")
    preferences = SavedSplitPreference.objects.filter(user=request.user)
    return render(request, "expenses/templates.html", {"templates": templates, "preferences": preferences})


@login_required
def template_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Enter a template name.")
        else:
            ExpenseTemplate.objects.create(
                user=request.user,
                name=name[:80],
                payload={
                    "description": request.POST.get("description", ""),
                    "amount": request.POST.get("amount", ""),
                    "split_method": request.POST.get("split_method") or "equal",
                    "notes": request.POST.get("notes", ""),
                },
            )
            messages.success(request, "Template saved. It does not create an expense until you use it.")
            return redirect("expenses:templates")
    return render(request, "expenses/template_form.html")


@login_required
def template_use(request, pk):
    template = get_object_or_404(ExpenseTemplate, pk=pk, user=request.user)
    request.session["expense_template"] = template.payload
    messages.info(request, f"“{template.name}” was copied into a new expense. Nothing is saved until you confirm.")
    return redirect("expenses:add")


@login_required
@require_POST
def template_delete(request, pk):
    get_object_or_404(ExpenseTemplate, pk=pk, user=request.user).delete()
    messages.success(request, "Template deleted.")
    return redirect("expenses:templates")


@login_required
def preference_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Enter a name.")
        else:
            SavedSplitPreference.objects.create(
                user=request.user,
                name=name[:80],
                split_method=request.POST.get("split_method") or "equal",
                currency=request.user.preferred_currency,
                payload={"note": request.POST.get("note", "")},
            )
            messages.success(request, "Split preference saved.")
            return redirect("expenses:templates")
    return render(request, "expenses/preference_form.html")


@login_required
@require_POST
def preference_delete(request, pk):
    get_object_or_404(SavedSplitPreference, pk=pk, user=request.user).delete()
    return redirect("expenses:templates")
