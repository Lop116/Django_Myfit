"""Task 6 - integration tests across modules.

Part 1 - permissions for every admin page and each role.
Part 2 - one realistic story end to end (register -> membership -> check-in ->
         class booking -> cancellation) with notifications and dashboard checks.
Part 3 - KNOWN GAPS found while merging, as expected failures. Each one flips to
         "unexpected success" when its owner fixes it - then remove the marker.
"""
import unittest
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
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
    MembershipChangeRequest,
    MembershipPlan,
    Notification,
)
from core.services import book_client_into_class, cancel_booking

User = get_user_model()

# Pages only an Admin should open (all must render for a superuser).
ADMIN_ONLY_PAGES = (
    "admin_dashboard", "client_manage", "manage_branches", "branch_add", "manage_coaches", "coach_add",
    "specialty_manage", "specialty_add", "manage_classes", "manage_bookings", "manage_payments",
    "manage_plans", "membership_requests", "assign_client_membership", "support_manage",
)


def make_user(username, role=None, **extra):
    user = User.objects.create_user(username, f"{username}@example.com", "pass12345", **extra)
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def delta(before, after, *path):
    for key in path:
        before, after = before[key], after[key]
    return after - before


class PermissionMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client_user = make_user("t6client", "Client")
        cls.coach_user = make_user("t6coach", "Coach")
        cls.superuser = User.objects.create_superuser("t6root", "root@example.com", "pass12345")

    def test_anonymous_clients_and_coaches_never_get_an_admin_page(self):
        for who in (None, self.client_user, self.coach_user):
            self.client.logout()
            if who:
                self.client.force_login(who)
            for name in ADMIN_ONLY_PAGES:
                with self.subTest(user=getattr(who, "username", "anonymous"), page=name):
                    self.assertIn(self.client.get(reverse(f"myfit:{name}")).status_code, (302, 403))

    def test_superuser_can_open_every_admin_page(self):
        self.client.force_login(self.superuser)
        for name in ADMIN_ONLY_PAGES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"myfit:{name}")).status_code, 200)

    def test_coach_pages_are_not_open_to_clients(self):
        self.client.force_login(self.client_user)
        for name in ("coach_dashboard", "coach_clients"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"myfit:{name}")).status_code, 403)

    def test_clients_cannot_use_the_staff_check_in_screens(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse("myfit:membership_scanner")).status_code, 403)

    def test_each_role_lands_on_its_own_dashboard_after_login(self):
        expected = {"t6client": "myfit:client_dashboard", "t6coach": "myfit:coach_dashboard",
                    "t6root": "myfit:admin_dashboard"}
        for username, destination in expected.items():
            with self.subTest(user=username):
                self.client.logout()
                response = self.client.post(reverse("myfit:login"), {"username": username, "password": "pass12345"})
                self.assertRedirects(response, reverse(destination), fetch_redirect_response=False)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(reverse("myfit:login"), {"username": "t6client", "password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_deactivated_client_cannot_log_in(self):
        self.client_user.is_active = False
        self.client_user.save()
        response = self.client.post(reverse("myfit:login"), {"username": "t6client", "password": "pass12345"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class EndToEndGymStoryTests(TestCase):
    """Register -> membership -> check-in -> book -> cancel, watching dashboard and notifications."""

    def setUp(self):
        self.before = get_dashboard_stats()
        self.today = timezone.localdate()
        self.branch = Branch.objects.create(name="T6 Trianon", address="Quatre Bornes")
        self.coach = CoachProfile.objects.create(user=make_user("t6coach", "Coach"), branch=self.branch)
        self.plan = MembershipPlan.objects.create(name="T6 Monthly", price="1500.00", duration_days=30)

    def gained(self, *path):
        return delta(self.before, get_dashboard_stats(), *path)

    def register(self, username):
        response = self.client.post(reverse("myfit:register"), {
            "first_name": username.title(), "last_name": "Test", "email": f"{username}@example.com",
            "username": username, "password1": "Str0ng!Passw0rd", "password2": "Str0ng!Passw0rd",
        })
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        return User.objects.get(username=username)

    def make_session(self, capacity=2):
        return ClassSession.objects.create(
            title="T6 Yoga", branch=self.branch, coach=self.coach,
            date=self.today + timedelta(days=1), time="08:00", capacity=capacity)

    def test_registration_creates_client_account_with_profile(self):
        user = self.register("t6newclient")

        self.assertTrue(user.groups.filter(name="Client").exists())
        self.assertTrue(ClientProfile.objects.filter(user=user).exists())
        self.assertEqual(self.gained("clients", "total"), 1)

    def test_membership_attendance_and_booking_flow_updates_dashboard(self):
        alice, bob, carol = (self.register(n) for n in ("t6alice", "t6bob", "t6carol"))
        self.assertEqual(self.gained("memberships", "active"), 0)

        # Admin assigns plans; overlapping assignment is rejected.
        membership = assign_membership(alice, self.plan, self.today)
        assign_membership(bob, self.plan, self.today)
        assign_membership(carol, self.plan, self.today)
        self.assertEqual(membership.agreed_price, self.plan.price)
        self.assertEqual(membership.end_date, self.today + timedelta(days=29))
        self.assertEqual(self.gained("memberships", "active"), 3)
        with self.assertRaises(ValidationError):
            assign_membership(alice, self.plan, self.today + timedelta(days=5))

        # Alice checks in; a duplicate check-in is rejected; check-out frees her.
        visit = check_in_membership(membership.pk)
        self.assertEqual(self.gained("attendance", "today"), 1)
        with self.assertRaises(ValidationError):
            check_in_membership(membership.pk)
        check_out_visit(visit.pk)
        check_in_membership(membership.pk)

        # Capacity 2: two bookings succeed; third and duplicate are refused.
        session = self.make_session(capacity=2)
        first = book_client_into_class(session.pk, alice.client_profile)
        book_client_into_class(session.pk, bob.client_profile)
        with self.assertRaises(ValidationError):
            book_client_into_class(session.pk, carol.client_profile)
        with self.assertRaises(ValidationError):
            book_client_into_class(session.pk, alice.client_profile)
        self.assertEqual(session.spaces_left, 0)
        self.assertEqual(self.gained("bookings", "confirmed"), 2)
        self.assertEqual(self.gained("classes", "scheduled"), 1)

        # Cancelling frees a space and keeps the history row.
        cancel_booking(first.pk, alice)
        self.assertEqual(session.spaces_left, 1)
        self.assertEqual(self.gained("bookings", "total"), 2)
        self.assertEqual(self.gained("bookings", "confirmed"), 1)
        book_client_into_class(session.pk, carol.client_profile)
        self.assertEqual(session.spaces_left, 0)

    def test_booking_requires_an_active_membership(self):
        dave = self.register("t6dave")
        with self.assertRaises(ValidationError):
            book_client_into_class(self.make_session().pk, dave.client_profile)

    def test_booking_and_cancellation_create_notifications(self):
        alice = self.register("t6alice")
        assign_membership(alice, self.plan, self.today)
        booking = book_client_into_class(self.make_session().pk, alice.client_profile)
        titles = list(Notification.objects.filter(user=alice).values_list("title", flat=True))
        self.assertEqual(titles, ["Class booking confirmed"])

        cancel_booking(booking.pk, alice)

        titles = list(Notification.objects.filter(user=alice).values_list("title", flat=True))
        self.assertCountEqual(titles, ["Class booking confirmed", "Class booking cancelled"])

    def test_failed_booking_leaves_no_notification(self):
        dave = self.register("t6dave")
        with self.assertRaises(ValidationError):
            book_client_into_class(self.make_session().pk, dave.client_profile)
        self.assertFalse(Notification.objects.filter(user=dave).exists())

    def test_a_client_cannot_cancel_someone_elses_booking(self):
        alice, bob = self.register("t6alice"), self.register("t6bob")
        assign_membership(alice, self.plan, self.today)
        booking = book_client_into_class(self.make_session().pk, alice.client_profile)

        with self.assertRaises(PermissionDenied):
            cancel_booking(booking.pk, bob)

        booking.refresh_from_db()
        self.assertEqual(booking.status, "Confirmed")

    def test_admin_can_remove_a_client_and_the_client_is_notified(self):
        alice = self.register("t6alice")
        assign_membership(alice, self.plan, self.today)
        booking = book_client_into_class(self.make_session().pk, alice.client_profile)
        admin = make_user("t6boss", "Admin")

        cancel_booking(booking.pk, admin)

        booking.refresh_from_db()
        self.assertEqual(booking.status, "Cancelled")
        self.assertTrue(Notification.objects.filter(user=alice, title="Class booking cancelled").exists())

    def test_another_coach_cannot_remove_a_client_from_my_class(self):
        alice = self.register("t6alice")
        assign_membership(alice, self.plan, self.today)
        booking = book_client_into_class(self.make_session().pk, alice.client_profile)
        other_coach = make_user("t6othercoach", "Coach")
        CoachProfile.objects.create(user=other_coach, branch=self.branch)

        with self.assertRaises(PermissionDenied):
            cancel_booking(booking.pk, other_coach)

    def test_admin_dashboard_page_reflects_the_story(self):
        alice = self.register("t6alice")
        assign_membership(alice, self.plan, self.today)
        self.client.force_login(make_user("t6boss", "Admin"))

        stats = self.client.get(reverse("myfit:admin_dashboard")).context["stats"]

        self.assertEqual(delta(self.before, stats, "clients", "total"), 1)
        self.assertEqual(delta(self.before, stats, "memberships", "active"), 1)


class KnownGapTests(TestCase):
    """Integration gaps found while merging. Each is reported to its owner."""

    @unittest.expectedFailure
    def test_coach_and_assignment_pages_render(self):
        # Ankush: coaching views load templates from myfit/Trial_html/, which a later
        # commit ("Repair") deleted, so these pages return 500.
        root = User.objects.create_superuser("t6root", "root@example.com", "pass12345")
        self.client.force_login(root)
        self.client.raise_request_exception = False
        self.assertEqual(self.client.get(reverse("myfit:coaching_assignments")).status_code, 200)

    @unittest.expectedFailure
    def test_membership_decision_notifies_the_client(self):
        # Deshrao / Task 5: approving or rejecting a membership change request creates no notification.
        plan = MembershipPlan.objects.create(name="T6 P", price="10.00", duration_days=30)
        other = MembershipPlan.objects.create(name="T6 Q", price="20.00", duration_days=30)
        client_user = make_user("t6client", "Client")
        today = timezone.localdate()
        membership = assign_membership(client_user, plan, today)
        change = MembershipChangeRequest.objects.create(membership=membership, requested_plan=other)
        root = User.objects.create_superuser("t6root", "root@example.com", "pass12345")
        self.client.force_login(root)

        self.client.post(reverse("myfit:review_membership_change_request", args=[change.pk, "approve"]))

        change.refresh_from_db()
        self.assertEqual(change.status, "approved")  # the decision itself works...
        self.assertTrue(Notification.objects.filter(user=client_user).exists())  # ...but nobody is told

    @unittest.expectedFailure
    def test_admin_role_alone_can_open_membership_pages(self):
        # Membership pages need is_staff + model permissions, the rest of the site only
        # checks the Admin group. A plain Admin-group user is locked out of these pages.
        self.client.force_login(make_user("t6boss", "Admin"))
        for name in ("manage_plans", "membership_requests", "assign_client_membership"):
            self.assertEqual(self.client.get(reverse(f"myfit:{name}")).status_code, 200)
