"""Admin dashboard + client management.

The database already holds starter data (migration 0014), so every number is
checked as "how much did it change" rather than as an absolute count.
"""
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.dashboard_services import get_dashboard_stats
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
    Payment,
    SupportTicket,
)


def make_user(username, role=None, **extra):
    user = User.objects.create_user(username, f"{username}@example.com", "pass12345", **extra)
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def dig(stats, path):
    for key in path:
        stats = stats[key]
    return stats


class StatsTestCase(TestCase):
    def setUp(self):
        self.before = get_dashboard_stats()
        self.today = timezone.localdate()

    def gained(self, *path):
        return dig(get_dashboard_stats(), path) - dig(self.before, path)


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
                self.client.force_login(make_user(f"{role.lower()}_x", role))
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
        self.client.force_login(User.objects.create_superuser("root", "root@example.com", "pass12345"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_admin_login_redirects_to_admin_dashboard(self):
        admin = make_user("login_admin", "Admin")
        response = self.client.post(
            reverse("myfit:login"),
            {
                "username": admin.username,
                "password": "pass12345",
                "next": reverse("myfit:home"),
            },
        )
        self.assertRedirects(response, self.url)

    def test_authenticated_admin_visiting_login_is_sent_to_dashboard(self):
        self.client.force_login(make_user("already_admin", "Admin"))
        response = self.client.get(reverse("myfit:login"))
        self.assertRedirects(response, self.url)


class DashboardStatsTests(StatsTestCase):
    def setUp(self):
        super().setUp()
        self.plan = MembershipPlan.objects.create(name="T6 Monthly", price="30.00", duration_days=30)

    def membership(self, username, start_offset, end_offset, status="active"):
        return ClientMembership.objects.create(
            user=make_user(username, "Client"),
            plan=self.plan,
            start_date=self.today + timedelta(days=start_offset),
            end_date=self.today + timedelta(days=end_offset),
            agreed_price="30.00",
            status=status,
        )

    def test_counts_clients_and_coaches_by_role(self):
        make_user("t6c1", "Client")
        make_user("t6c2", "Client")
        make_user("t6c3", "Client", is_active=False)
        make_user("t6coach", "Coach")
        make_user("t6boss", "Admin")

        self.assertEqual(self.gained("clients", "total"), 3)
        self.assertEqual(self.gained("clients", "active"), 2)
        self.assertEqual(self.gained("coaches", "total"), 1)
        self.assertEqual(self.gained("coaches", "active"), 1)

    def test_counts_branches(self):
        Branch.objects.create(name="T6 Branch A", address="Quatre Bornes")
        Branch.objects.create(name="T6 Branch B", address="Port Louis", is_active=False)

        self.assertEqual(self.gained("branches", "total"), 2)
        self.assertEqual(self.gained("branches", "active"), 1)

    def test_membership_counts_follow_dates_not_just_stored_status(self):
        self.membership("t6m_active", -5, 20)
        self.membership("t6m_started", -1, 29, "scheduled")  # stored scheduled, already started
        self.membership("t6m_future", 5, 35, "scheduled")    # not started: neither active nor expired
        self.membership("t6m_lapsed", -40, -10)              # stored active, dates passed
        self.membership("t6m_expired", -40, -10, "expired")
        self.membership("t6m_suspended", -5, 20, "suspended")

        self.assertEqual(self.gained("memberships", "active"), 2)
        self.assertEqual(self.gained("memberships", "expired"), 2)
        self.assertEqual(self.gained("memberships", "suspended"), 1)

    def test_dashboard_matches_the_membership_model_current_status(self):
        for i, (start, end, status) in enumerate(
            [(-5, 20, "active"), (-1, 29, "scheduled"), (5, 35, "scheduled"),
             (-40, -10, "active"), (-40, -10, "expired"), (-5, 20, "suspended")]
        ):
            self.membership(f"t6u{i}", start, end, status)
        by_status = {}
        for m in ClientMembership.objects.all():
            by_status[m.current_status] = by_status.get(m.current_status, 0) + 1

        memberships = get_dashboard_stats()["memberships"]

        self.assertEqual(memberships["active"], by_status.get("active", 0))
        self.assertEqual(memberships["expired"], by_status.get("expired", 0))
        self.assertEqual(memberships["suspended"], by_status.get("suspended", 0))

    def test_pending_membership_requests_only_counts_pending(self):
        other = MembershipPlan.objects.create(name="T6 Annual", price="300.00", duration_days=365)
        MembershipChangeRequest.objects.create(membership=self.membership("t6r1", -5, 20), requested_plan=other)
        MembershipChangeRequest.objects.create(
            membership=self.membership("t6r2", -5, 20), requested_plan=other, status="approved")

        self.assertEqual(self.gained("memberships", "pending_requests"), 1)

    def test_class_and_booking_counts(self):
        branch = Branch.objects.create(name="T6 Branch", address="Quatre Bornes")
        coach = CoachProfile.objects.create(user=make_user("t6coach", "Coach"), branch=branch)

        def make_session(title, status):
            return ClassSession.objects.create(
                title=title, branch=branch, coach=coach, date=self.today + timedelta(days=1),
                time="09:00", capacity=5, status=status)

        scheduled = make_session("Yoga", "Scheduled")
        make_session("Spin", "Scheduled")
        make_session("HIIT", "Cancelled")
        make_session("Old class", "Completed")
        c1 = ClientProfile.objects.create(user=make_user("t6b1", "Client"))
        c2 = ClientProfile.objects.create(user=make_user("t6b2", "Client"))
        ClassBooking.objects.create(session=scheduled, client=c1)
        ClassBooking.objects.create(session=scheduled, client=c2, status="Cancelled")

        self.assertEqual(self.gained("classes", "scheduled"), 2)
        self.assertEqual(self.gained("classes", "cancelled"), 1)
        self.assertEqual(self.gained("bookings", "total"), 2)
        self.assertEqual(self.gained("bookings", "confirmed"), 1)

    def test_attendance_counts_only_todays_check_ins(self):
        membership, other = self.membership("t6a1", -5, 20), self.membership("t6a2", -5, 20)
        AttendanceVisit.objects.create(membership=membership, check_in=timezone.now())
        AttendanceVisit.objects.create(
            membership=other, check_in=timezone.now() - timedelta(days=1),
            check_out=timezone.now() - timedelta(days=1, hours=-1))

        self.assertEqual(self.gained("attendance", "today"), 1)

    def test_open_support_tickets_excludes_resolved(self):
        for status in ("open", "progress", "resolved"):
            SupportTicket.objects.create(
                name="N", email="n@example.com", topic="t", subject=status, message="m", status=status)

        self.assertEqual(self.gained("support", "open"), 2)

    def test_dashboard_page_shows_the_numbers(self):
        make_user("t6p1", "Client")
        make_user("t6p2", "Client")
        make_user("t6pcoach", "Coach")
        self.membership("t6pshown", -5, 20)
        self.client.force_login(make_user("t6boss", "Admin"))

        response = self.client.get(reverse("myfit:admin_dashboard"))

        stats = response.context["stats"]
        self.assertEqual(stats["clients"]["total"] - self.before["clients"]["total"], 3)
        self.assertEqual(stats["coaches"]["total"] - self.before["coaches"]["total"], 1)
        self.assertContains(response, f'id="stat-clients">{stats["clients"]["total"]}<')
        self.assertContains(response, f'id="stat-mem-active">{stats["memberships"]["active"]}<')


class PaymentDashboardTests(TestCase):
    def setUp(self):
        self.admin = make_user("payment_admin", "Admin")
        self.client_user = make_user("payment_client", "Client")
        self.client_profile = ClientProfile.objects.create(user=self.client_user)
        self.client.force_login(self.admin)

    def test_dashboard_sums_paid_transactions_and_counts_pending(self):
        Payment.objects.create(client=self.client_profile, amount="75.00", status=Payment.Status.PAID)
        Payment.objects.create(client=self.client_profile, amount="20.00", status=Payment.Status.PENDING)
        Payment.objects.create(client=self.client_profile, amount="10.00", status=Payment.Status.REFUNDED)

        response = self.client.get(reverse("myfit:admin_dashboard"))

        self.assertEqual(response.context["stats"]["payments"]["transactions"], 3)
        self.assertEqual(response.context["stats"]["payments"]["paid_total"], 75)
        self.assertEqual(response.context["stats"]["payments"]["pending"], 1)
        self.assertContains(response, 'id="stat-payments-paid">Rs 75.00')

    def test_admin_can_record_a_payment_transaction(self):
        response = self.client.post(
            reverse("myfit:manage_payments"),
            {
                "client": self.client_profile.pk,
                "amount": "125.50",
                "payment_date": timezone.localdate().isoformat(),
                "status": Payment.Status.PAID,
                "payment_method": "Cash",
                "reference": "receipt-01",
            },
        )

        self.assertRedirects(response, reverse("myfit:manage_payments"))
        payment = Payment.objects.get(reference="receipt-01")
        self.assertEqual(payment.client, self.client_profile)
        self.assertEqual(payment.recorded_by, self.admin)

    def test_admin_management_pages_load_shared_styles(self):
        for page in (
            "manage_bookings",
            "manage_payments",
            "manage_plans",
            "assign_client_membership",
            "membership_requests",
            "attendance_dashboard",
        ):
            with self.subTest(page=page):
                response = self.client.get(reverse(f"myfit:{page}"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "css/admin_dashboard.css")

        classes_response = self.client.get(reverse("myfit:manage_classes"))
        self.assertEqual(classes_response.status_code, 200)
        self.assertContains(classes_response, "css/manage_classes.css")


class ClientManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("t6boss", "Admin")
        self.alice = make_user("t6alice", "Client", first_name="Alice", last_name="Zzramdin")
        self.bob = make_user("t6bob", "Client", first_name="Bob", last_name="Zzjugoo", is_active=False)
        ClientProfile.objects.create(user=self.alice, phone="5712345")
        self.coach = make_user("t6coach", "Coach")
        self.client.force_login(self.admin)

    def usernames(self, **params):
        response = self.client.get(reverse("myfit:client_manage"), params)
        return [u.username for u in response.context["clients"]]

    def test_list_contains_clients_but_not_coaches_or_admins(self):
        names = self.usernames()
        self.assertIn("t6alice", names)
        self.assertIn("t6bob", names)
        self.assertNotIn("t6coach", names)
        self.assertNotIn("t6boss", names)

    def test_search_by_name_email_and_phone(self):
        for term, expected in (("zzramdin", ["t6alice"]), ("t6bob@example", ["t6bob"]),
                               ("5712345", ["t6alice"]), ("zzzznothing", [])):
            with self.subTest(term=term):
                self.assertEqual(self.usernames(q=term), expected)

    def test_filter_by_status(self):
        self.assertEqual(self.usernames(q="zz", status="active"), ["t6alice"])
        self.assertEqual(self.usernames(q="zz", status="inactive"), ["t6bob"])

    def test_toggle_deactivates_and_reactivates(self):
        url = reverse("myfit:client_toggle", args=[self.alice.pk])
        self.client.post(url)
        self.alice.refresh_from_db()
        self.assertFalse(self.alice.is_active)
        self.client.post(url)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.is_active)

    def test_toggle_requires_post(self):
        self.assertEqual(self.client.get(reverse("myfit:client_toggle", args=[self.alice.pk])).status_code, 405)

    def test_coaches_and_superusers_cannot_be_managed_as_clients(self):
        root = User.objects.create_superuser("t6root", "root@example.com", "pass12345")
        root.groups.add(Group.objects.get(name="Client"))
        for user in (self.coach, root):
            with self.subTest(user=user.username):
                self.assertEqual(self.client.post(reverse("myfit:client_toggle", args=[user.pk])).status_code, 404)
                user.refresh_from_db()
                self.assertTrue(user.is_active)

    def test_edit_updates_user_and_profile(self):
        response = self.client.post(
            reverse("myfit:client_edit", args=[self.alice.pk]),
            {"account-first_name": "Alicia", "account-last_name": "Zzramdin",
             "account-email": "alicia@example.com", "profile-date_of_birth": "",
             "profile-gender": "F", "profile-phone": "5799999"},
        )

        self.assertRedirects(response, reverse("myfit:client_manage"))
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.first_name, "Alicia")
        self.assertEqual(self.alice.email, "alicia@example.com")
        self.assertEqual(self.alice.client_profile.phone, "5799999")

    def test_edit_rejects_email_used_by_another_account(self):
        response = self.client.post(
            reverse("myfit:client_edit", args=[self.alice.pk]),
            {"account-first_name": "A", "account-last_name": "R", "account-email": "T6BOB@example.com",
             "profile-date_of_birth": "", "profile-gender": "", "profile-phone": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already using this email")
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.email, "t6alice@example.com")

    def test_only_admins_can_use_client_management(self):
        urls = [reverse("myfit:client_manage"), reverse("myfit:client_edit", args=[self.alice.pk])]
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
