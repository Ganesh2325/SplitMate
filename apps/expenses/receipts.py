import os
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from apps.common.exceptions import AuthorizationError, DomainError
from apps.expenses.access import can_edit_expense, can_view_expense
from apps.expenses.models import ExpenseAttachment
from apps.groups.access import active_membership, is_manager


SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"%PDF", "application/pdf", ".pdf"),
)


def detect_upload(uploaded):
    header = uploaded.read(16)
    uploaded.seek(0)
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp", ".webp"
    for magic, content_type, extension in SIGNATURES:
        if header.startswith(magic):
            return content_type, extension
    raise DomainError("Upload a JPEG, PNG, WebP, or PDF receipt.")


def store_receipt(expense, uploaded, user):
    if not can_view_expense(user, expense):
        raise AuthorizationError("You cannot add a receipt to this expense.")
    if uploaded.size > settings.RECEIPT_MAX_BYTES:
        raise DomainError("Receipts must be 5 MB or smaller.")
    content_type, extension = detect_upload(uploaded)
    if content_type.startswith("image/"):
        try:
            image = Image.open(uploaded)
            image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise DomainError("That image could not be read.") from exc
        finally:
            uploaded.seek(0)
    original = os.path.basename(getattr(uploaded, "name", "receipt"))[:200] or "receipt"
    content = uploaded.read()
    attachment = ExpenseAttachment(
        expense=expense,
        uploaded_by=user,
        original_name=original,
        content_type=content_type,
        size=len(content),
    )
    attachment.file.save(f"{uuid.uuid4().hex}{extension}", ContentFile(content), save=True)
    return attachment


def delete_receipt(attachment, user):
    expense = attachment.expense
    allowed = attachment.uploaded_by_id == user.id or can_edit_expense(user, expense)
    if expense.group_id:
        allowed = allowed or is_manager(active_membership(user, expense.group))
    if not allowed:
        raise AuthorizationError("You cannot remove this receipt.")
    attachment.delete()


def scan_receipt(uploaded):
    """Return suggestions only. Scanning never writes an expense."""
    if not settings.ENABLE_OCR:
        return {
            "available": False,
            "message": "Receipt scanning is not enabled on this server. Enter the amount yourself.",
        }
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return {
            "available": False,
            "message": "The OCR library is not installed. Enter the amount yourself.",
        }
    return {
        "available": False,
        "message": "Automatic scanning did not produce a confirmed total. Enter the amount yourself.",
    }
