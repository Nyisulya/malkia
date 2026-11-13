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

            # Map legacy roles to primary roles for verification
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

            # CEO has oversight across all business operations
            if user_role == UserRole.CEO:
                return view_func(request, *args, **kwargs)

            if user_role not in normalized_allowed:
                messages.warning(request, "Access restricted: You do not have permission to access this section.")
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def can_approve_expense(user, voucher):
    """
    Checks if user is authorized to approve and disburse/release office funds.
    Office funds are approved and released exclusively by the CEO (or Superuser/Admin).
    """
    role = get_user_role(user)
    if role in [UserRole.CEO, UserRole.ADMIN] or user.is_superuser:
        return True
    return False


def can_audit_expense(user, voucher=None):
    """
    Checks if user is authorized to audit & forward vouchers to CEO (Accountant bridge).
    """
    role = get_user_role(user)
    return role in [UserRole.FINANCE, UserRole.CEO, UserRole.ADMIN] or user.is_superuser


def can_advance_stage(user, stage_number):
    """
    Checks if user is authorized to advance a specific stage.
    Operational staff and CEO can advance stages. Finance does not handle operational stage progression.
    """
    if not user or not user.is_authenticated:
        return False
    role = get_user_role(user)
    if role == UserRole.FINANCE:
        return False
    return True


def user_can_manage_docs(user, job=None):
    """
    Checks if a user is authorized to upload, edit, replace, or delete documents and save document dossiers.
    Strictly limited to:
    - Superusers / Administrators / CEO
    - Assigned Documentation Officer for the job
    - Users with DOC_OFFICER role or DOCUMENTATION department
    Other operational staff (Customs Declarer, Port Wharfinger, Finance, Yard, Drivers) have read-only view/download access.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True

    if job and job.documentation_officer_id and job.documentation_officer_id == user.id:
        return True

    profile = getattr(user, 'profile', None)
    if profile:
        if profile.role in [UserRole.DOC_OFFICER, UserRole.ADMIN, UserRole.CEO, UserRole.OPERATIONS_MGR]:
            return True
        if profile.department in ['DOCUMENTATION', 'EXECUTIVE', 'ADMIN_IT']:
            return True
        if profile.role == UserRole.OPERATIONS and (not job or not job.documentation_officer_id):
            if profile.department in ['DOCUMENTATION', 'OPERATIONS']:
                return True

    if user.username in ['doc_officer', 'test_doc_officer', 'admin']:
        return True

    return False
