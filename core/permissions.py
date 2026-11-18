from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from .models import UserRole


def get_user_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return UserRole.CEO
    if hasattr(user, 'profile'):
        role = user.profile.role
        if role in [UserRole.CEO, UserRole.ADMIN]:
            return UserRole.CEO
        elif role == UserRole.FINANCE:
            return UserRole.FINANCE
        else:
            return UserRole.OPERATIONS
    return UserRole.OPERATIONS


def role_required(allowed_roles, redirect_url='dashboard'):
    """
    Role-Based Access Control decorator strictly enforcing the 3 primary roles:
    1. OPERATIONS (All operational staff: Operations Manager, Documentation, Customs, Port, Yard)
    2. FINANCE (Accountant / Financial officers)
    3. CEO (Executive Management / Admin / Superuser)
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Please log in to access this page.")
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_role = get_user_role(request.user)

            normalized_allowed = set()
            for r in allowed_roles:
                if r in [UserRole.CEO, UserRole.ADMIN]:
                    normalized_allowed.add(UserRole.CEO)
                    normalized_allowed.add(UserRole.ADMIN)
                elif r == UserRole.FINANCE:
                    normalized_allowed.add(UserRole.FINANCE)
                else:
                    normalized_allowed.add(UserRole.OPERATIONS)
                    normalized_allowed.add(r)

            if user_role == UserRole.CEO:
                return view_func(request, *args, **kwargs)

            if user_role not in normalized_allowed:
                messages.warning(request, "Access restricted: You do not have permission to access this section.")
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def can_approve_expense(user, voucher):
    role = get_user_role(user)
    if role in [UserRole.CEO, UserRole.ADMIN] or user.is_superuser:
        return True
    return False


def can_audit_expense(user, voucher=None):
    role = get_user_role(user)
    return role in [UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN] or user.is_superuser


def can_advance_stage(user, stage_number):
    if not user or not user.is_authenticated:
        return False
    role = get_user_role(user)
    if role == UserRole.FINANCE:
        return False
    return True


def user_can_manage_docs(user, job=None):
    """
    All operational staff (OPERATIONS) and administrators/CEO can upload, edit,
    replace, or delete documents and save document dossiers. Finance has read-only access.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    role = get_user_role(user)
    if role == UserRole.FINANCE:
        return False
    return True
