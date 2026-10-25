#Loick login permission
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
ROLE_NAMES = ("Client", "Coach", "Admin")

def has_role(user, role):
    if not user.is_authenticated or not user.is_active: #user.is_authenticated checks whether the user is logged in.
                                                        #user.is_active indicates whether their account is enabled.
        return False
    if role == "Admin" and user.is_superuser:
        return True
    return user.groups.filter(name=role).exists()

def dashboard_name(user): #This function determines which dashboard a user should be directed to according to their role.
    if has_role(user, "Admin"):
        return "myfit:admin_dashboard"
    if has_role(user, "Coach"):
        return "myfit:coach_dashboard"
    if has_role(user, "Client"):
        return "myfit:client_dashboard"
    return "myfit:home"


def role_required(role):# """Require login plus a named role; authenticated wrong-role users get 403."""

    def decorator(view_func): 
        @login_required#ensures the user is logged in. Otherwise, they're redirected to the login page.
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, role):#verifies whether the user belongs to the required group (Client, Coach, or Admin). If not, Django returns a 403 Forbidden error.
                raise PermissionDenied("You are not allowed to access this page.")
            return view_func(request, *args, **kwargs) #executes and displays the requested page.
        return wrapped
    return decorator
