from functools import wraps
from decimal import Decimal
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .models import UserRole

def get_user_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return UserRole.ADMIN
    if hasattr(user, 'profile'):
        return user.profile.role
    return UserRole.DOC_OFFICER


def role_required(allowed_roles, redirect_url='dashboard'):
    """
    Decorator to enforce Role-Based Access Control on views.
    Accepts a single role string or a list/tuple of allowed roles.
    Superusers and ADMINs are granted access to all views.
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    # Always include ADMIN
    if UserRole.ADMIN not in allowed_roles:
        allowed_roles = list(allowed_roles) + [UserRole.ADMIN]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Please log in to access this page.")
                return redirect('login')

            role = get_user_role(request.user)

            if role not in allowed_roles:
                messages.error(
                    request,
                    f"Access Denied: Your current role ({request.user.profile.get_role_display() if hasattr(request.user, 'profile') else role}) does not have permission to perform this action or view this page."
                )
                # If driver, redirect to driver console
                if role == UserRole.DRIVER:
                    return redirect('driver_delivery')
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def can_approve_expense(user, voucher):
    """
    Checks if user is authorized to approve this specific voucher
    based on the multi-tier approval matrix:
    - Amount <= 500,000: Operations Manager, Finance, CEO, Admin
    - 500,001 <= Amount <= 2,000,000: Finance, CEO, Admin
    - Amount > 2,000,000: CEO / Managing Director, Admin
    """
    role = get_user_role(user)
    if role == UserRole.ADMIN or user.is_superuser or role == UserRole.CEO:
        return True

    amt = voucher.amount
    if amt <= Decimal('500000'):
        return role in [UserRole.OPERATIONS_MGR, UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN]
    elif amt <= Decimal('2000000'):
        return role in [UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN]
    else:
        # High value (> 2M) approved by CEO / Managing Director, Admin, or Finance
        return role in [UserRole.CEO, UserRole.ADMIN, UserRole.FINANCE]


def can_advance_stage(user, stage_number):
    """
    Checks if user is authorized to advance a specific stage.
    CEO is strictly executive oversight (read-only).
    """
    role = get_user_role(user)
    if role == UserRole.CEO:
        return False

    if role in [UserRole.ADMIN, UserRole.OPERATIONS_MGR]:
        return True

    if stage_number == 1:
        return role == UserRole.DOC_OFFICER
    elif stage_number == 2:
        return role == UserRole.CLEARING_OFFICER
    elif stage_number == 3:
        return role in [UserRole.FINANCE, UserRole.CLEARING_OFFICER]
    elif stage_number == 4:
        return role in [UserRole.PORT_OFFICER, UserRole.CLEARING_OFFICER]
    elif stage_number == 5:
        return role == UserRole.PORT_OFFICER
    elif stage_number == 6:
        return role in [UserRole.FINANCE, UserRole.PORT_OFFICER]
    elif stage_number == 7:
        return role in [UserRole.PORT_OFFICER, UserRole.DISPATCH_OFFICER]
    elif stage_number == 8:
        return role in [UserRole.DISPATCH_OFFICER, UserRole.DOC_OFFICER]
    elif stage_number == 9:
        return role in [UserRole.DISPATCH_OFFICER, UserRole.DOC_OFFICER]
    return False
