from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from apps.categories.models import ExpenseCategory
from apps.expenses.models import Expense
from apps.expenses.selectors import categories_for


@login_required
def category_list(request):
    query = (request.GET.get("q") or "").strip()
    categories = categories_for(request.user)
    if query:
        categories = categories.filter(name__icontains=query)
    return render(request, "categories/list.html", {"categories": categories, "query": query})


@login_required
def category_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Enter a category name.")
        else:
            slug = slugify(name)[:50] or "category"
            base = slug
            index = 2
            while ExpenseCategory.objects.filter(owner=request.user, slug=slug).exists():
                slug = f"{base}-{index}"[:50]
                index += 1
            ExpenseCategory.objects.create(name=name[:80], slug=slug, icon="bi-tag", owner=request.user)
            messages.success(request, "Category added for your account.")
            return redirect("categories:list")
    return render(request, "categories/form.html")


@login_required
def category_delete(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk, owner=request.user, is_system=False)
    if request.method == "POST":
        if Expense.objects.filter(category=category).exists():
            messages.error(request, "This category is used by expenses, so it stays in the record.")
        else:
            category.delete()
            messages.success(request, "Category deleted.")
        return redirect("categories:list")
    return render(request, "categories/delete.html", {"category": category})
