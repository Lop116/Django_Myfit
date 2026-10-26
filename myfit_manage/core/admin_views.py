"""Admin-only views (Task 6). Separate file to avoid merge conflicts in views.py."""
from django.shortcuts import render
from django.utils import timezone

from .dashboard_services import get_dashboard_stats
from .permissions import role_required


@role_required("Admin")
def admin_dashboard(request):
    return render(
        request,
        "myfit/admin_dashboard.html",
        {"stats": get_dashboard_stats(), "today": timezone.localdate()},
    )

