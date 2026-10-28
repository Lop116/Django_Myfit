"""Task 6 - integration tests across modules.

Part 1 checks permissions for every admin page and each role.
Part 2 runs one realistic story end to end (register -> membership -> check-in
-> class booking -> cancellation) and checks the Admin dashboard after each step.
Part 3 lists KNOWN GAPS as expected failures: each flips to "unexpected success"
when a teammate fixes it, which is the cue to delete the expectedFailure marker.
"""
import unittest
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.dashboard_services import get_dashboard_stats
from core.membership_services import assign_membership, check_in_membership, check_out_visit
from core.models import (
    Branch,
    ClassSession,
    ClientMembership,
    ClientProfile,
    CoachProfile,
    MembershipPlan,
    Notification,
)
from core.services import book_client_into_class, cancel_booking

User = get_user_model()

# Pages only an Admin should open.
ADMIN_ONLY_PAGES = (
    "admin_dashboard",
    "client_manage",
    "manage_branches",
    "manage_coaches",
    "manage_bookings",
    "manage_payments",
    "manage_plans",
    "membership_requests",
    "assign_client_membership",
    "coaching_assignments",
)
# Admin-only pages whose templates are missing from the repo (Task 1 / Task 5 owner).
ADMIN_PAGES_WITH_MISSING_TEMPLATES = (
    "branch_add",
    "coach_add",
    "specialty_manage",
    "specialty_add",
    "support_manage",
)


def make_user(username, role=None, **extra):
    user = User.objects.create_user(username, f"{username}@example.com", "pass12345", **extra)
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


class PermissionMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client_user = make_user("client1", "Client")
        cls.coach_user = make_user("coach1", "Coach")
        cls.superuser = User.objects.create_superuser("root", "root@example.com", "pass12345")

    def test_anonymous_clients_and_coaches_never_get_an_admin_page(self):
        for who in (None, self.client_user, self.coach_user):
            if who:
                self.client.force_login(who)
            else:
                self.client.logout()
            for name in ADMIN_ONLY_PAGES + ADMIN_PAGES_WITH_MISSING_TEMPLATES:
                with self.subTest(user=getattr(who, "username", "anonymous"), page=name):
                    response = self.client.get(reverse(f"myfit:{name}"))
                    self.assertIn(response.status_code, (302, 403))

    def test_superuser_can_open_every_working_admin_page(self):
        self.client.force_login(self.superuser)
        for name in ADMIN_ONLY_PAGES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"myfit:{name}")).status_code, 200)

    def test_coach_pages_are_not_open_to_clients(self):
        self.client.force_login(self.client_user)
        for name in ("coach_dashboard", "coach_clients", "coaching_clients"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"myfit:{name}")).status_code, 403)

    def test_clients_cannot_use_the_admin_check_in_screens(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse("myfit:membership_scanner")).status_code, 403)

    def test_each_role_lands_on_its_own_dashboard_after_login(self):
        expected = {
            "client1": "myfit:client_dashboard",
            "coach1": "myfit:coach_dashboard",
            "root": "myfit:admin_dashboard",
        }
        passwords = {"client1": "pass12345", "coach1": "pass12345", "root": "pass12345"}
        for username, destination in expected.items():
            with self.subTest(user=username):
                self.client.logout()
                response = self.client.post(
                    reverse("myfit:login"), {"username": username, "password": passwords[username]}
                )
                self.assertRedirects(
                    response, reverse(destination), fetch_redirect_response=False
                )

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse("myfit:login"), {"username": "client1", "password": "nope"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_deactivated_client_cannot_log_in(self):
        self.client_user.is_active = False
        self.client_user.save()
        response = self.client.post(
            reverse("myfit:login"), {"username": "client1", "password": "pass12345"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class EndToEndGymStoryTests(TestCase):
    """Register -> membership -> check-in -> book -> cancel, watching the dashboard."""

    def setUp(self):
        self.today = timezone.localdate()
        self.branch = Branch.objects.create(name="Trianon", address="Quatre Bornes")
        coach_user = make_user("coach1", "Coach")
        self.coach = CoachProfile.objects.create(user=coach_user, branch=self.branch)
        self.plan = MembershipPlan.objects.create(name="Monthly", price="1500.00", duration_days=30)

    def register(self, username):
        response = self.client.post(
            reverse("myfit:register"),
            {
                "first_name": username.title(),
                "last_name": "Test",
                "email": f"{username}@example.com",
                "username": username,
                "password1": "Str0ng!Passw0rd",
                "password2": "Str0ng!Passw0rd",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        return User.objects.get(username=username)

    def test_registration_creates_client_account_with_profile(self):
        user = self.register("newclient")

        self.assertTrue(user.groups.filter(name="Client").exists())
        self.assertTrue(ClientProfile.objects.filter(user=user).exists())
        self.assertEqual(get_dashboard_stats()["clients"]["total"], 1)

    def test_membership_attendance_and_booking_flow_updates_dashboard(self):
        # 1. Two clients register.
        alice, bob = self.register("alice"), self.register("bob")
        stats = get_dashboard_stats()
        self.assertEqual(stats["clients"]["total"], 2)
        self.assertEqual(stats["memberships"]["active"], 0)

        # 2. Admin assigns Alice a plan.
        membership = assign_membership(alice, self.plan, self.today)
        self.assertEqual(membership.agreed_price, self.plan.price)
        self.assertEqual(membership.end_date, self.today + timedelta(days=29))
        self.assertEqual(get_dashboard_stats()["memberships"]["active"], 1)

        # 3. Overlapping assignment is rejected.
        with self.assertRaises(ValidationError):
            assign_membership(alice, self.plan, self.today + timedelta(days=5))

        # 4. Alice checks in; a second check-in is rejected; check-out frees her.
        visit = check_in_membership(membership.pk)
        self.assertEqual(get_dashboard_stats()["attendance"]["today"], 1)
        with self.assertRaises(ValidationError):
            check_in_membership(membership.pk)
        check_out_visit(visit.pk)
        check_in_membership(membership.pk)

        # 5. Bob has no membership: his membership cannot check in.
        self.assertFalse(ClientMembership.objects.filter(user=bob).exists())

        # 6. Class of capacity 2: two bookings succeed, the third is refused.
        session = ClassSession.objects.create(
            title="Yoga", branch=self.branch, coach=self.coach,
            date=self.today + timedelta(days=1), time="08:00", capacity=2,
        )
        carol = self.register("carol")
        first = book_client_into_class(session.pk, alice.client_profile)
        book_client_into_class(session.pk, bob.client_profile)
        with self.assertRaises(ValidationError):
            book_client_into_class(session.pk, carol.client_profile)
        with self.assertRaises(ValidationError):
            book_client_into_class(session.pk, alice.client_profile)  # duplicate
        self.assertEqual(session.spaces_left, 0)
        stats = get_dashboard_stats()
        self.assertEqual(stats["bookings"], {"total": 2, "confirmed": 2})
        self.assertEqual(stats["classes"]["scheduled"], 1)

        # 7. Alice cancels: a space opens, the history row is kept.
        cancel_booking(first.pk, alice)
        self.assertEqual(session.spaces_left, 1)
        stats = get_dashboard_stats()
        self.assertEqual(stats["bookings"], {"total": 2, "confirmed": 1})

        # 8. Carol can now take the freed space.
        book_client_into_class(session.pk, carol.client_profile)
        self.assertEqual(session.spaces_left, 0)

    def test_a_client_cannot_cancel_someone_elses_booking(self):
        alice, bob = self.register("alice"), self.register("bob")
        session = ClassSession.objects.create(
            title="Yoga", branch=self.branch, coach=self.coach,
            date=self.today + timedelta(days=1), time="08:00", capacity=5,
        )
        booking = book_client_into_class(session.pk, alice.client_profile)

        with self.assertRaises(ValidationError):
            cancel_booking(booking.pk, bob)

        booking.refresh_from_db()
        self.assertEqual(booking.status, "Confirmed")

    def test_admin_dashboard_page_reflects_the_story(self):
        alice = self.register("alice")
        assign_membership(alice, self.plan, self.today)
        admin = make_user("boss", "Admin")
        self.client.force_login(admin)

        response = self.client.get(reverse("myfit:admin_dashboard"))

        self.assertContains(response, 'id="stat-clients">1<')
        self.assertContains(response, 'id="stat-mem-active">1<')


class KnownGapTests(TestCase):
    """Integration gaps found while merging. Each is reported to its owner.

    expectedFailure keeps the suite green today and turns into an
    "unexpected success" the moment the gap is fixed - then remove the marker.
    """

    @unittest.expectedFailure
    def test_admin_pages_listed_in_the_spec_all_render(self):
        # Task 1 / Task 5: these views point at templates that are not in the repo.
        root = User.objects.create_superuser("root", "root@example.com", "pass12345")
        self.client.force_login(root)
        self.client.raise_request_exception = False
        broken = [
            name for name in ADMIN_PAGES_WITH_MISSING_TEMPLATES
            if self.client.get(reverse(f"myfit:{name}")).status_code != 200
        ]
        self.assertEqual(broken, [])

    @unittest.expectedFailure
    def test_booking_creates_a_stored_notification(self):
        # Task 3 / Task 5: bookings only print to the console today.
        branch = Branch.objects.create(name="Trianon", address="Quatre Bornes")
        coach = CoachProfile.objects.create(user=make_user("coach1", "Coach"), branch=branch)
        client_user = make_user("client1", "Client")
        profile = ClientProfile.objects.create(user=client_user)
        session = ClassSession.objects.create(
            title="Yoga", branch=branch, coach=coach,
            date=timezone.localdate() + timedelta(days=1), time="08:00", capacity=2,
        )

        book_client_into_class(session.pk, profile)

        self.assertTrue(Notification.objects.filter(user=client_user).exists())

    @unittest.expectedFailure
    def test_admin_role_alone_can_open_membership_pages(self):
        # Membership pages need is_staff + model permissions, the rest of the
        # site only checks the Admin group. A plain Admin-group user is locked out.
        admin = make_user("boss", "Admin")
        self.client.force_login(admin)
        for name in ("manage_plans", "membership_requests", "assign_client_membership"):
            self.assertEqual(self.client.get(reverse(f"myfit:{name}")).status_code, 200)
