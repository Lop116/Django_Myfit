from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import dashboard_services
from core.models import (
    AttendanceVisit,
    Branch,
    ClassBooking,
    ClassSession,
    ClientMembership,
    ClientProfile,
    CoachProfile,
    MembershipChangeRequest,
    MembershipPlan,
    SupportTicket,
)


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
    """Every number is checked against real rows built with the real models."""

    def setUp(self):
        self.today = timezone.localdate()
        self.plan = MembershipPlan.objects.create(name="Monthly", price="30.00", duration_days=30)

    def membership(self, username, start_offset, end_offset, status="active"):
        user = make_user(username, "Client")
        return ClientMembership.objects.create(
            user=user,
            plan=self.plan,
            start_date=self.today + timedelta(days=start_offset),
            end_date=self.today + timedelta(days=end_offset),
            agreed_price="30.00",
            status=status,
        )

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

        self.assertEqual(
            dashboard_services.get_dashboard_stats()["branches"], {"total": 2, "active": 1}
        )

    def test_membership_counts_follow_dates_not_just_stored_status(self):
        self.membership("m_active", -5, 20)                       # valid now
        self.membership("m_scheduled_started", -1, 29, "scheduled")  # stored scheduled, already started
        self.membership("m_future", 5, 35, "scheduled")           # not started: neither active nor expired
        self.membership("m_lapsed", -40, -10)                     # stored active, dates passed
        self.membership("m_expired", -40, -10, "expired")
        self.membership("m_suspended", -5, 20, "suspended")

        memberships = dashboard_services.get_dashboard_stats()["memberships"]

        self.assertEqual(memberships["active"], 2)
        self.assertEqual(memberships["expired"], 2)
        self.assertEqual(memberships["suspended"], 1)

    def test_dashboard_counts_match_membership_current_status(self):
        for i, (start, end, status) in enumerate(
            [(-5, 20, "active"), (-1, 29, "scheduled"), (5, 35, "scheduled"),
             (-40, -10, "active"), (-40, -10, "expired"), (-5, 20, "suspended")]
        ):
            self.membership(f"u{i}", start, end, status)
        by_status = {}
        for m in ClientMembership.objects.all():
            by_status[m.current_status] = by_status.get(m.current_status, 0) + 1

        memberships = dashboard_services.get_dashboard_stats()["memberships"]

        self.assertEqual(memberships["active"], by_status.get("active", 0))
        self.assertEqual(memberships["expired"], by_status.get("expired", 0))
        self.assertEqual(memberships["suspended"], by_status.get("suspended", 0))

    def test_pending_membership_requests_only_counts_pending(self):
        other_plan = MembershipPlan.objects.create(name="Annual", price="300.00", duration_days=365)
        first = self.membership("r1", -5, 20)
        second = self.membership("r2", -5, 20)
        MembershipChangeRequest.objects.create(membership=first, requested_plan=other_plan)
        MembershipChangeRequest.objects.create(
            membership=second, requested_plan=other_plan, status="approved"
        )

        self.assertEqual(
            dashboard_services.get_dashboard_stats()["memberships"]["pending_requests"], 1
        )

    def test_class_and_booking_counts(self):
        branch = Branch.objects.create(name="Trianon", address="Quatre Bornes")
        coach = CoachProfile.objects.create(user=make_user("coach1", "Coach"), branch=branch)
        make_session = lambda title, status: ClassSession.objects.create(
            title=title, branch=branch, coach=coach, date=self.today + timedelta(days=1),
            time="09:00", capacity=5, status=status,
        )
        scheduled = make_session("Yoga", "Scheduled")
        make_session("Spin", "Scheduled")
        make_session("HIIT", "Cancelled")
        make_session("Old class", "Completed")
        c1 = ClientProfile.objects.create(user=make_user("c1", "Client"))
        c2 = ClientProfile.objects.create(user=make_user("c2", "Client"))
        ClassBooking.objects.create(session=scheduled, client=c1)
        ClassBooking.objects.create(session=scheduled, client=c2, status="Cancelled")

        stats = dashboard_services.get_dashboard_stats()

        self.assertEqual(stats["classes"], {"scheduled": 2, "cancelled": 1})
        self.assertEqual(stats["bookings"], {"total": 2, "confirmed": 1})

    def test_attendance_counts_only_todays_check_ins(self):
        membership = self.membership("a1", -5, 20)
        other = self.membership("a2", -5, 20)
        AttendanceVisit.objects.create(membership=membership, check_in=timezone.now())
        yesterday = AttendanceVisit.objects.create(
            membership=other, check_in=timezone.now() - timedelta(days=1),
            check_out=timezone.now() - timedelta(days=1, hours=-1),
        )

        self.assertEqual(dashboard_services.get_dashboard_stats()["attendance"]["today"], 1)
        self.assertIsNotNone(yesterday.pk)

    def test_open_support_tickets_excludes_resolved(self):
        for status in ("open", "progress", "resolved"):
            SupportTicket.objects.create(
                name="N", email="n@example.com", topic="t", subject=status, message="m", status=status
            )

        self.assertEqual(dashboard_services.get_dashboard_stats()["support"]["open"], 2)

    def test_dashboard_page_shows_the_numbers(self):
        make_user("c1", "Client")
        make_user("c2", "Client")
        make_user("coach1", "Coach")
        self.membership("shown", -5, 20)
        self.client.force_login(make_user("boss", "Admin"))

        response = self.client.get(reverse("myfit:admin_dashboard"))

        self.assertContains(response, 'id="stat-clients">3<')
        self.assertContains(response, 'id="stat-coaches">1<')
        self.assertContains(response, 'id="stat-mem-active">1<')


class ClientManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", "Admin")
        self.alice = make_user("alice", "Client", first_name="Alice", last_name="Ramdin")
        self.bob = make_user("bob", "Client", first_name="Bob", last_name="Jugoo", is_active=False)
        ClientProfile.objects.create(user=self.alice, phone="5712345")
        self.coach = make_user("coach1", "Coach")
        self.client.force_login(self.admin)

    def test_list_shows_clients_only(self):
        response = self.client.get(reverse("myfit:client_manage"))

        usernames = [u.username for u in response.context["clients"]]
        self.assertEqual(usernames, ["alice", "bob"])

    def test_search_by_name_email_and_phone(self):
        url = reverse("myfit:client_manage")
        for term, expected in (("ramdin", ["alice"]), ("bob@example", ["bob"]), ("5712345", ["alice"]), ("zzz", [])):
            with self.subTest(term=term):
                response = self.client.get(url, {"q": term})
                self.assertEqual([u.username for u in response.context["clients"]], expected)

    def test_filter_by_status(self):
        url = reverse("myfit:client_manage")
        active = self.client.get(url, {"status": "active"}).context["clients"]
        inactive = self.client.get(url, {"status": "inactive"}).context["clients"]
        self.assertEqual([u.username for u in active], ["alice"])
        self.assertEqual([u.username for u in inactive], ["bob"])

    def test_toggle_deactivates_and_reactivates(self):
        url = reverse("myfit:client_toggle", args=[self.alice.pk])
        self.client.post(url)
        self.alice.refresh_from_db()
        self.assertFalse(self.alice.is_active)
        self.client.post(url)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.is_active)

    def test_toggle_requires_post(self):
        response = self.client.get(reverse("myfit:client_toggle", args=[self.alice.pk]))
        self.assertEqual(response.status_code, 405)

    def test_coaches_and_superusers_cannot_be_managed_as_clients(self):
        root = User.objects.create_superuser("root", "root@example.com", "pass12345")
        root.groups.add(Group.objects.get(name="Client"))
        for user in (self.coach, root):
            with self.subTest(user=user.username):
                response = self.client.post(reverse("myfit:client_toggle", args=[user.pk]))
                self.assertEqual(response.status_code, 404)
                user.refresh_from_db()
                self.assertTrue(user.is_active)

    def test_edit_updates_user_and_profile(self):
        response = self.client.post(
            reverse("myfit:client_edit", args=[self.alice.pk]),
            {
                "account-first_name": "Alicia",
                "account-last_name": "Ramdin",
                "account-email": "alicia@example.com",
                "profile-date_of_birth": "",
                "profile-gender": "F",
                "profile-phone": "5799999",
            },
        )

        self.assertRedirects(response, reverse("myfit:client_manage"))
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.first_name, "Alicia")
        self.assertEqual(self.alice.email, "alicia@example.com")
        self.assertEqual(self.alice.client_profile.phone, "5799999")

    def test_edit_rejects_email_used_by_another_account(self):
        response = self.client.post(
            reverse("myfit:client_edit", args=[self.alice.pk]),
            {"account-first_name": "A", "account-last_name": "R", "account-email": "BOB@example.com",
             "profile-date_of_birth": "", "profile-gender": "", "profile-phone": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already using this email")
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.email, "alice@example.com")

    def test_only_admins_can_use_client_management(self):
        urls = [
            reverse("myfit:client_manage"),
            reverse("myfit:client_edit", args=[self.alice.pk]),
        ]
        toggle = reverse("myfit:client_toggle", args=[self.alice.pk])
        for who in (self.alice, self.coach):
            self.client.force_login(who)
            for url in urls:
                with self.subTest(user=who.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(toggle).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(urls[0]).status_code, 302)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.is_active)
