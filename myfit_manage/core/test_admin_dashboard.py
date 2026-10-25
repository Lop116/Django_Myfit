from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from core import dashboard_services
from core.models import Branch, MembershipPass


def make_user(username, role=None, **extra):
    user = User.objects.create_user(username, f"{username}@example.com", "pass12345", **extra)
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


class AdminDashboardAccessTests(TestCase):
    def setUp(self):
        self.url = reverse("myfit:admin_dashboard")

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("myfit:login"), response["Location"])

    def test_client_and_coach_are_forbidden(self):
        for role in ("Client", "Coach"):
            with self.subTest(role=role):
                self.client.force_login(make_user(f"{role.lower()}1", role))
                self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_user_without_role_is_forbidden(self):
        self.client.force_login(make_user("norole"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_admin_group_member_can_open_dashboard(self):
        self.client.force_login(make_user("boss", "Admin"))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "myfit/admin_dashboard.html")

    def test_superuser_can_open_dashboard(self):
        self.client.force_login(
            User.objects.create_superuser("root", "root@example.com", "pass12345")
        )
        self.assertEqual(self.client.get(self.url).status_code, 200)


class DashboardStatsTests(TestCase):
    def test_counts_clients_and_coaches_by_role(self):
        make_user("c1", "Client")
        make_user("c2", "Client")
        make_user("c3", "Client", is_active=False)
        make_user("coach1", "Coach")
        make_user("boss", "Admin")

        stats = dashboard_services.get_dashboard_stats()

        self.assertEqual(stats["clients"], {"total": 3, "active": 2})
        self.assertEqual(stats["coaches"], {"total": 1, "active": 1})

    def test_counts_branches(self):
        Branch.objects.create(name="Trianon", address="Quatre Bornes")
        Branch.objects.create(name="Caudan", address="Port Louis", is_active=False)

        stats = dashboard_services.get_dashboard_stats()

        self.assertEqual(stats["branches"], {"total": 2, "active": 1})

    def test_membership_numbers_from_existing_membership_pass(self):
        # Fallback path: only valid while ClientMembership is not merged yet.
        if dashboard_services._get_model("ClientMembership") is not None:
            self.skipTest("ClientMembership merged; fallback no longer used")
        from datetime import timedelta
        from django.utils import timezone

        today = timezone.localdate()
        specs = [
            ("m1", "active", today + timedelta(days=5)),
            ("m2", "active", today - timedelta(days=1)),
            ("m3", "expired", today - timedelta(days=9)),
            ("m4", "pending", None),
        ]
        for name, status, expiry in specs:
            MembershipPass.objects.create(
                user=make_user(name, "Client"), plan="access", status=status, expiry_date=expiry
            )

        memberships = dashboard_services.get_dashboard_stats()["memberships"]

        self.assertEqual(memberships["active"], 1)
        self.assertEqual(memberships["expired"], 2)
        self.assertEqual(memberships["pending_requests"], 1)

    def test_missing_models_give_none_instead_of_crashing(self):
        real = dashboard_services._get_model
        hidden = {"ClientMembership", "MembershipPass", "MembershipChangeRequest",
                  "ClassSession", "ClassBooking", "ClientBooking", "AttendanceVisit"}
        with mock.patch.object(
            dashboard_services, "_get_model",
            side_effect=lambda name: None if name in hidden else real(name),
        ):
            stats = dashboard_services.get_dashboard_stats()

        self.assertEqual(stats["memberships"],
                         {"active": None, "expired": None, "pending_requests": None})
        self.assertEqual(stats["classes"], {"scheduled": None, "cancelled": None})
        self.assertIsNone(stats["bookings"]["total"])
        self.assertIsNone(stats["attendance"]["today"])

    def test_dashboard_page_shows_the_numbers(self):
        make_user("c1", "Client")
        make_user("c2", "Client")
        make_user("coach1", "Coach")
        self.client.force_login(make_user("boss", "Admin"))

        response = self.client.get(reverse("myfit:admin_dashboard"))

        self.assertContains(response, 'id="stat-clients">2<', html=False)
        self.assertContains(response, 'id="stat-coaches">1<', html=False)
