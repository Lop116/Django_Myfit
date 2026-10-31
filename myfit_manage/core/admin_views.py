"""Admin-only views (Task 6). Separate file to avoid merge conflicts in views.py."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .dashboard_services import get_dashboard_stats
from .forms import AccountDetailsForm, AdminClientCreationForm, ClientProfileForm
from .models import ClientProfile
from .permissions import role_required
from .services import membership_booking_status

User = get_user_model()


@role_required("Admin")
def admin_dashboard(request):
    return render(
        request,
        "myfit/admin_dashboard.html",
        {"stats": get_dashboard_stats(), "today": timezone.localdate()},
    )


def _client_users():
    """Client accounts only: never staff or superusers, whatever else they are."""
    return User.objects.filter(groups__name="Client", is_superuser=False).distinct()


@role_required("Admin")
def client_manage(request):
    """Search and filter client accounts."""
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    clients = _client_users().select_related("client_profile").order_by("username")
    if q:
        clients = clients.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(client_profile__phone__icontains=q)
        )
    
    if status in ("active", "needs_membership"):
        clients = clients.filter(is_active=True)
    elif status == "inactive":
        clients = clients.filter(is_active=False)
    # Account status (User.is_active) and membership status are separate; show both.
    clients = list(clients)
    for client in clients:
        client.membership_state, client.membership = membership_booking_status(client)
    if status == "needs_membership":
        clients = [c for c in clients if c.membership_state in ("none", "expired")]
    return render(
        request,
        "myfit/client_manage.html",
        {"clients": clients, "q": q, "status": status, "total": _client_users().count()},
    )


@role_required("Admin")
@transaction.atomic
def client_add(request):
    form = AdminClientCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        group, _ = Group.objects.get_or_create(name="Client")
        user.groups.add(group)
        ClientProfile.objects.create(user=user, phone=form.cleaned_data["phone"])
        messages.success(request, f"{user.get_full_name() or user.username} added.")
        return redirect("myfit:client_manage")
    return render(request, "myfit/client_add.html", {"form": form})


@role_required("Admin")
@transaction.atomic
def client_edit(request, user_id):
    """Edit a client's name, email and profile details."""
    user = get_object_or_404(_client_users(), pk=user_id)
    profile, _ = ClientProfile.objects.get_or_create(user=user)
    account_form = AccountDetailsForm(request.POST or None, instance=user, prefix="account")
    profile_form = ClientProfileForm(request.POST or None, instance=profile, prefix="profile")
    if request.method == "POST" and account_form.is_valid() and profile_form.is_valid():
        email = account_form.cleaned_data["email"].strip()
        if email and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            account_form.add_error("email", "An account is already using this email.")
        else:
            account_form.save()
            profile_form.save()
            messages.success(request, f"{user.username} updated.")
            return redirect("myfit:client_manage")
    return render(
        request,
        "myfit/client_form.html",
        {"client_user": user, "account_form": account_form, "profile_form": profile_form},
    )


@role_required("Admin")
@require_POST
def client_toggle(request, user_id):
    """Activate or deactivate a client account (the account is never deleted)."""
    user = get_object_or_404(_client_users(), pk=user_id)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    state = "activated" if user.is_active else "deactivated"
    messages.success(request, f"{user.username} {state}.")
    return redirect("myfit:client_manage")


@role_required("Admin")
@require_POST
def member_toggle(request, profile_id):
    profile = get_object_or_404(ClientProfile.objects.select_related("user"), pk=profile_id)
    user = profile.user
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    if not user.is_active:
        profile.bookings.filter(status="Confirmed").update(
            status="Cancelled",
            cancelled_at=timezone.now(),
        )
    state = "activated" if user.is_active else "deactivated"
    messages.success(request, f"{user.username} {state}.")
    return redirect("myfit:client_manage")
