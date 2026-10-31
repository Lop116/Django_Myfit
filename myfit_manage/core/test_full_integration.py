"""End-to-end integration tests for the repaired MyFit application.

They run against the real starter data created by migrations 0014 and 0017.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Branch, ClassBooking, ClassSession, ClientMembership, ClientProfile,
    CoachClientAssignment, CoachProfile, CoachSpecialty, MembershipPlan,
    Notification, SupportTicket, WorkoutRecord,
)

User = get_user_model()
PASSWORD = 'Integration-Test-Pass-2026!'


def make_user(username, role=None, **extra):
    user = User.objects.create_user(username, f'{username}@example.com', PASSWORD, **extra)
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def make_client(username, plan_name='My Access XL'):
    user = make_user(username, 'Client', first_name=username.title())
    profile = ClientProfile.objects.create(user=user)
    if plan_name:
        plan = MembershipPlan.objects.get(name=plan_name)
        today = timezone.localdate()
        ClientMembership.objects.create(
            user=user, plan=plan, start_date=today, end_date=today + timedelta(days=29),
            agreed_price=plan.price, status='active',
        )
    return profile


def future_session(**overrides):
    values = {
        'title': 'Integration Test Class', 'category': 'HIIT',
        'branch': Branch.objects.get(name='Trianon'),
        'coach': CoachProfile.objects.get(user__username='demo_daniel'),
        'date': timezone.localdate() + timedelta(days=3),
        'time': timezone.datetime(2000, 1, 1, 10, 0).time(),
        'capacity': 5, 'status': 'Scheduled',
    }
    values.update(overrides)
    return ClassSession.objects.create(**values)


class StarterDataTests(TestCase):
    def test_required_starter_records_exist_and_are_linked(self):
        self.assertEqual(
            set(Branch.objects.values_list('name', flat=True)),
            {'Caudan Waterfront', 'Trianon', 'Riche Terre', 'Plaisance Mall'},
        )
        self.assertEqual(Branch.objects.get(name='Plaisance Mall').operational_status, 'Coming soon')
        plans = dict(MembershipPlan.objects.values_list('name', 'price'))
        self.assertEqual(plans, {
            'My Access': Decimal('1249.00'), 'My Access XL': Decimal('1399.00'),
            'My Access Premium': Decimal('1549.00'),
        })
        self.assertFalse(MembershipPlan.objects.get(name='My Access').allows_classes)
        self.assertGreaterEqual(CoachSpecialty.objects.count(), 6)

        coaches = CoachProfile.objects.filter(user__username__startswith='demo_')
        self.assertEqual(coaches.count(), 4)
        for coach in coaches:
            self.assertIsNotNone(coach.branch_id)
            self.assertTrue(coach.specialties.exists())
            self.assertTrue(coach.user.groups.filter(name='Coach').exists())

        clients = ClientProfile.objects.filter(user__username__startswith='demo_client')
        self.assertEqual(clients.count(), 2)
        for client in clients:
            self.assertTrue(ClientMembership.objects.filter(user=client.user).exists())
            self.assertTrue(CoachClientAssignment.objects.filter(client=client).exists())
            self.assertTrue(Notification.objects.filter(user=client.user).exists())

        self.assertGreaterEqual(ClassSession.objects.count(), 6)
        self.assertEqual(ClassBooking.objects.filter(
            status='Confirmed', client__in=clients).count(), 2)

    def test_single_admin_with_no_usable_password_in_repository(self):
        admin = User.objects.get(username='myfit_admin')
        self.assertTrue(admin.is_superuser and admin.is_staff)
        self.assertTrue(admin.groups.filter(name='Admin').exists())
        for user in User.objects.filter(username__in=['myfit_admin', 'demo_maya', 'demo_client1']):
            self.assertFalse(user.has_usable_password())
        self.assertTrue(Group.objects.get(name='Admin').permissions.filter(
            codename='change_membershipplan').exists())

    def test_rerunning_migrate_does_not_duplicate_or_restore_starter_data(self):
        counts = {m: m.objects.count() for m in (Branch, CoachProfile, ClassSession, MembershipPlan, User)}
        trianon = Branch.objects.get(name='Trianon')
        trianon.name, trianon.is_active = 'Trianon Renamed', False
        trianon.save()
        plan = MembershipPlan.objects.get(name='My Access')
        plan.price = Decimal('1299.00')
        plan.save()
        CoachSpecialty.objects.filter(name='Zumba').delete()
        Branch.objects.filter(name='Plaisance Mall').delete()

        call_command('migrate', verbosity=0)

        self.assertFalse(Branch.objects.filter(name='Trianon').exists())
        self.assertFalse(Branch.objects.get(name='Trianon Renamed').is_active)
        self.assertEqual(MembershipPlan.objects.get(name='My Access').price, Decimal('1299.00'))
        self.assertFalse(CoachSpecialty.objects.filter(name='Zumba').exists())
        self.assertFalse(Branch.objects.filter(name='Plaisance Mall').exists())
        self.assertEqual(Branch.objects.count(), counts[Branch] - 1)
        for model in (CoachProfile, ClassSession, MembershipPlan, User):
            self.assertEqual(model.objects.count(), counts[model])


class AdminManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user('integration-admin', 'Admin')
        self.client.force_login(self.admin)

    def test_branch_crud_and_public_visibility(self):
        response = self.client.post(reverse('myfit:branch_add'), {
            'name': 'Flacq Test Club', 'address': 'Central Flacq',
            'operational_status': 'Open', 'is_active': 'on',
        })
        self.assertRedirects(response, reverse('myfit:manage_branches'))
        branch = Branch.objects.get(name='Flacq Test Club')
        self.assertContains(self.client.get(reverse('myfit:branches')), 'Flacq Test Club')
        self.assertContains(self.client.get(reverse('myfit:home')), 'FLACQ TEST CLUB')

        self.client.post(reverse('myfit:branch_edit', args=[branch.pk]), {
            'name': 'Flacq Edited', 'address': 'Central Flacq',
            'operational_status': 'Maintenance', 'is_active': 'on',
        })
        self.assertContains(self.client.get(reverse('myfit:branches')), 'Flacq Edited')

        self.client.post(reverse('myfit:branch_toggle', args=[branch.pk]))
        self.assertNotContains(self.client.get(reverse('myfit:branches')), 'Flacq Edited')
        self.assertContains(self.client.get(reverse('myfit:manage_branches')), 'Flacq Edited')

        self.client.post(reverse('myfit:branch_delete', args=[branch.pk]))
        self.assertFalse(Branch.objects.filter(pk=branch.pk).exists())

    def test_branch_with_history_cannot_be_removed(self):
        branch = Branch.objects.get(name='Caudan Waterfront')
        response = self.client.post(reverse('myfit:branch_delete', args=[branch.pk]), follow=True)
        self.assertTrue(Branch.objects.filter(pk=branch.pk).exists())
        self.assertContains(response, 'Hide it instead')

    def test_coach_crud_updates_public_page(self):
        specialty = CoachSpecialty.objects.get(name='Yoga')
        branch = Branch.objects.get(name='Riche Terre')
        self.client.post(reverse('myfit:coach_add'), {
            'username': 'coach-new', 'first_name': 'Priya', 'last_name': 'Ramdin',
            'email': 'priya@example.com', 'password': PASSWORD, 'branch': branch.pk,
            'specialties': [specialty.pk], 'bio': 'Mobility coach', 'is_active': 'on',
        })
        coach = CoachProfile.objects.get(user__username='coach-new')
        self.assertTrue(coach.user.check_password(PASSWORD))
        self.assertTrue(coach.user.groups.filter(name='Coach').exists())
        self.assertContains(self.client.get(reverse('myfit:coaches')), 'PRIYA RAMDIN')

        maya = CoachProfile.objects.get(user__username='demo_maya')
        self.client.post(reverse('myfit:coach_edit', args=[maya.pk]), {
            'username': 'demo_maya', 'first_name': 'Maya', 'last_name': 'Robertson',
            'email': maya.user.email, 'branch': maya.branch_id, 'is_active': 'on',
        })
        self.assertContains(self.client.get(reverse('myfit:coaches')), 'MAYA ROBERTSON')

        self.client.post(reverse('myfit:coach_toggle', args=[maya.pk]))
        self.assertNotContains(self.client.get(reverse('myfit:coaches')), 'MAYA ROBERTSON')
        page = self.client.get(reverse('myfit:manage_coaches'))
        self.assertContains(page, 'Robertson')
        self.assertContains(page, 'assigned class')

    def test_member_management(self):
        self.client.post(reverse('myfit:member_add'), {
            'username': 'member-new', 'first_name': 'Leela', 'last_name': 'Doe',
            'email': 'leela@example.com', 'phone': '5250 0000',
            'password': PASSWORD, 'is_active': 'on',
        })
        member = ClientProfile.objects.get(user__username='member-new')
        self.assertTrue(member.user.groups.filter(name='Client').exists())
        self.assertEqual(member.phone, '5250 0000')
        page = self.client.get(reverse('myfit:manage_members'))
        self.assertContains(page, 'Leela Doe')
        self.assertContains(page, 'demo_client1@example.invalid')

        client1 = ClientProfile.objects.get(user__username='demo_client1')
        booking = ClassBooking.objects.get(client=client1, status='Confirmed')
        self.client.post(reverse('myfit:member_toggle', args=[client1.pk]))
        client1.user.refresh_from_db()
        booking.refresh_from_db()
        self.assertFalse(client1.user.is_active)
        self.assertEqual(booking.status, 'Cancelled')  # place released, row kept
        self.assertTrue(ClientMembership.objects.filter(user=client1.user).exists())

    def test_plan_edit_updates_public_pricing(self):
        plan = MembershipPlan.objects.get(name='My Access Premium')
        response = self.client.post(reverse('myfit:edit_membership_plan', args=[plan.pk]), {
            'name': 'My Access Premium', 'price': '1599.00', 'duration_days': 30,
            'benefits': plan.benefits, 'allows_classes': 'on', 'is_active': 'on',
        })
        self.assertRedirects(response, reverse('myfit:manage_plans'))
        self.assertContains(self.client.get(reverse('myfit:plans')), '1599')
        self.assertContains(self.client.get(reverse('myfit:home')), '1599')

    def test_class_create_validation_publish_and_cancel(self):
        coach = CoachProfile.objects.get(user__username='demo_sarah')
        data = {
            'title': 'Draft Pilates', 'category': 'Mobility', 'description': 'Test',
            'branch': coach.branch_id, 'coach': coach.pk,
            'date': (timezone.localdate() + timedelta(days=4)).isoformat(),
            'time': '09:00', 'end_time': '08:00', 'capacity': 0, 'status': 'Draft',
        }
        response = self.client.post(reverse('myfit:class_session_add'), data)
        self.assertEqual(response.status_code, 200)  # invalid end time + capacity
        self.assertFalse(ClassSession.objects.filter(title='Draft Pilates').exists())
        past = dict(data, end_time='10:00', capacity=8,
                    date=(timezone.localdate() - timedelta(days=1)).isoformat())
        self.assertEqual(self.client.post(reverse('myfit:class_session_add'), past).status_code, 200)

        valid = dict(data, end_time='10:00', capacity=8)
        self.assertRedirects(self.client.post(reverse('myfit:class_session_add'), valid),
                             reverse('myfit:manage_classes'))
        session = ClassSession.objects.get(title='Draft Pilates')
        self.assertNotContains(self.client.get(reverse('myfit:classes')), 'Draft Pilates')
        self.assertTrue(Notification.objects.filter(user=coach.user, title='Class assigned').exists())

        self.client.post(reverse('myfit:class_session_status', args=[session.pk]), {'action': 'publish'})
        self.assertContains(self.client.get(reverse('myfit:classes')), 'Draft Pilates')

        member = make_client('class-member')
        ClassBooking.objects.create(session=session, client=member)
        self.client.post(reverse('myfit:class_session_status', args=[session.pk]), {'action': 'cancel'})
        session.refresh_from_db()
        self.assertEqual(session.status, 'Cancelled')
        self.assertEqual(ClassBooking.objects.get(session=session).status, 'Cancelled')
        self.assertTrue(Notification.objects.filter(user=member.user, title='Class cancelled').exists())
        self.assertNotContains(self.client.get(reverse('myfit:classes')), 'Draft Pilates')

    def test_dashboard_statistics_match_database(self):
        stats = self.client.get(reverse('myfit:admin_dashboard')).context['stats']
        self.assertEqual(stats['branches']['total'], Branch.objects.count())
        self.assertEqual(stats['bookings']['total'], ClassBooking.objects.count())
        self.assertEqual(stats['bookings']['confirmed'], ClassBooking.objects.filter(status='Confirmed').count())
        self.assertEqual(stats['classes']['scheduled'], ClassSession.objects.filter(status='Scheduled').count())
        self.assertEqual(stats['memberships']['active'], 2)
        manage = self.client.get(reverse('myfit:manage_branches'))
        self.assertEqual(manage.context['total_branch_count'], Branch.objects.count())


class BookingWorkflowTests(TestCase):
    def setUp(self):
        self.member = make_client('booking-member')
        self.client.force_login(self.member.user)
        self.session = future_session(capacity=1)

    def book(self, session=None):
        return self.client.post(reverse('myfit:book_class', args=[(session or self.session).pk]), follow=True)

    def test_valid_booking_then_duplicate_then_full(self):
        self.book()
        booking = ClassBooking.objects.get(session=self.session, client=self.member)
        self.assertEqual(booking.status, 'Confirmed')
        self.assertTrue(Notification.objects.filter(user=self.member.user, title='Class booking confirmed').exists())
        self.assertContains(self.client.get(reverse('myfit:client_bookings')), 'Integration Test Class')

        response = self.book()
        self.assertContains(response, 'already have a confirmed booking')
        other = make_client('second-member')
        self.client.force_login(other.user)
        self.assertContains(self.book(), 'fully booked')
        self.assertEqual(ClassBooking.objects.filter(session=self.session, status='Confirmed').count(), 1)

    def test_ineligible_bookings_are_rejected(self):
        no_plan = make_client('no-plan-member', plan_name=None)
        self.client.force_login(no_plan.user)
        self.assertContains(self.book(), 'active MyFit membership is required')

        basic = make_client('basic-member', plan_name='My Access')
        self.client.force_login(basic.user)
        self.assertContains(self.book(), 'does not include group classes')

        self.client.force_login(self.member.user)
        draft = future_session(title='Unpublished', status='Draft')
        self.assertContains(self.book(draft), 'no longer available')
        cancelled = future_session(title='Cancelled one', status='Cancelled')
        self.assertContains(self.book(cancelled), 'no longer available')
        self.assertFalse(ClassBooking.objects.filter(client__in=[no_plan, basic, self.member]).exists())

    def test_cancellation_keeps_history_and_frees_place(self):
        self.book()
        booking = ClassBooking.objects.get(session=self.session)
        self.assertEqual(self.session.spaces_left, 0)
        self.client.post(reverse('myfit:cancel_booking', args=[booking.pk]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'Cancelled')
        self.assertIsNotNone(booking.cancelled_at)
        self.assertEqual(self.session.spaces_left, 1)
        self.assertTrue(Notification.objects.filter(
            user=self.session.coach.user, title='Client cancelled a booking').exists())
        page = self.client.get(reverse('myfit:client_bookings'))
        self.assertEqual(page.context['cancelled_count'], 1)
        # Rebooking after cancellation is allowed and creates a new history row.
        self.book()
        self.assertEqual(ClassBooking.objects.filter(session=self.session).count(), 2)

    def test_member_cannot_cancel_another_members_booking(self):
        other = make_client('other-member')
        booking = ClassBooking.objects.create(session=future_session(title='Other'), client=other)
        response = self.client.post(reverse('myfit:cancel_booking', args=[booking.pk]))
        self.assertEqual(response.status_code, 403)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'Confirmed')


class RoleAndAccountTests(TestCase):
    def test_registration_login_logout_and_password_hashing(self):
        response = self.client.post(reverse('myfit:register'), {
            'first_name': 'Nina', 'last_name': 'Ally', 'email': 'nina@example.com',
            'username': 'nina-ally', 'password1': PASSWORD, 'password2': PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='nina-ally')
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(user.groups.filter(name='Client').exists())
        self.assertTrue(ClientProfile.objects.filter(user=user).exists())

        self.client.post(reverse('myfit:logout'))
        response = self.client.post(reverse('myfit:login'), {'username': 'nina-ally', 'password': PASSWORD})
        self.assertRedirects(response, reverse('myfit:client_dashboard'))
        self.client.post(reverse('myfit:logout'))
        self.assertEqual(self.client.get(reverse('myfit:client_dashboard')).status_code, 302)

    def test_role_restrictions(self):
        client_user = make_client('role-client').user
        coach_user = User.objects.get(username='demo_daniel')
        admin_pages = ('manage_members', 'manage_branches', 'manage_coaches', 'admin_dashboard',
                       'manage_bookings', 'support_manage', 'coaching_assignments')
        for user in (client_user, coach_user):
            self.client.force_login(user)
            for page in admin_pages:
                with self.subTest(user=user.username, page=page):
                    self.assertEqual(self.client.get(reverse(f'myfit:{page}')).status_code, 403)
        self.client.force_login(client_user)
        self.assertEqual(self.client.get(reverse('myfit:manage_classes')).status_code, 403)
        self.assertEqual(self.client.get(reverse('myfit:coach_dashboard')).status_code, 403)

        # A coach may manage only their own classes.
        self.client.force_login(coach_user)
        foreign = ClassSession.objects.exclude(coach__user=coach_user).first()
        self.assertEqual(self.client.get(reverse('myfit:class_session_edit', args=[foreign.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('myfit:class_session_status', args=[foreign.pk]),
                                          {'action': 'cancel'}).status_code, 403)
        listed = self.client.get(reverse('myfit:manage_classes')).context['classes']
        self.assertTrue(all(s.coach.user_id == coach_user.pk for s in listed))

    def test_admin_role_account_can_use_membership_tools(self):
        # Admin-role users (not superusers) receive permissions from migration 0017.
        admin = make_user('role-admin', 'Admin')
        self.client.force_login(admin)
        for page in ('manage_plans', 'assign_client_membership', 'membership_requests',
                     'attendance_dashboard', 'membership_scanner'):
            with self.subTest(page=page):
                self.assertEqual(self.client.get(reverse(f'myfit:{page}')).status_code, 200)

    def test_notifications_belong_to_their_recipient(self):
        owner = User.objects.get(username='demo_client1')
        note = Notification.objects.filter(user=owner).first()
        intruder = make_client('nosy-member').user
        self.client.force_login(intruder)
        self.assertEqual(self.client.post(reverse('myfit:notification_read', args=[note.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('myfit:notification_list')), note.message)
        owner.set_password(PASSWORD)
        owner.save()
        self.client.force_login(owner)
        self.assertContains(self.client.get(reverse('myfit:notification_list')), note.title)

    def test_profile_edit_is_limited_to_four_details(self):
        member = make_client('profile-member')
        self.client.force_login(member.user)
        response = self.client.post(reverse('myfit:edit_profile'), {
            'account-first_name': 'Ravi', 'account-last_name': 'Seeb',
            'account-email': 'ravi@example.com', 'profile-phone': '5711 2233',
        })
        self.assertRedirects(response, reverse('myfit:edit_profile'))
        member.refresh_from_db()
        member.user.refresh_from_db()
        self.assertEqual((member.user.first_name, member.phone), ('Ravi', '5711 2233'))
        self.assertEqual(set(response.wsgi_request and self.client.get(
            reverse('myfit:edit_profile')).context['profile_form'].fields), {'phone'})


class MemberFeatureTests(TestCase):
    def setUp(self):
        self.member = make_client('feature-member')
        self.client.force_login(self.member.user)

    def test_workout_records_are_persisted_per_member(self):
        self.client.post(reverse('myfit:workouts'), {
            'action': 'add', 'exercise': 'Deadlift', 'workout_date': timezone.localdate().isoformat(),
            'sets': 3, 'reps': 5, 'weight': '100', 'notes': '',
        })
        record = WorkoutRecord.objects.get(user=self.member.user, exercise='Deadlift')
        self.assertContains(self.client.get(reverse('myfit:workouts')), 'Deadlift')
        self.assertContains(self.client.get(reverse('myfit:progress')), 'Deadlift')
        other = make_client('feature-other')
        self.client.force_login(other.user)
        self.assertNotContains(self.client.get(reverse('myfit:workouts')), 'Deadlift')
        response = self.client.post(reverse('myfit:workouts'), {'action': 'delete', 'workout_id': record.pk})
        self.assertEqual(response.status_code, 404)

    def test_support_ticket_persists_and_is_private(self):
        response = self.client.post(reverse('myfit:create_support_ticket'), {
            'subject': 'Locker issue', 'description': 'My locker at Trianon does not close properly.',
        })
        ticket = SupportTicket.objects.get(subject='Locker issue')
        self.assertRedirects(response, reverse('myfit:support_ticket_detail', args=[ticket.pk]))
        self.client.force_login(make_client('ticket-intruder').user)
        self.assertEqual(self.client.get(reverse('myfit:support_ticket_detail', args=[ticket.pk])).status_code, 403)

    def test_contact_enquiry_is_saved(self):
        self.client.logout()
        self.client.post(reverse('myfit:contact'), {
            'kind': 'enquiry', 'name': 'Visitor', 'email': 'visitor@example.com',
            'topic': 'Membership', 'subject': 'Prices', 'message': 'What does XL include exactly?',
        })
        self.assertTrue(SupportTicket.objects.filter(email='visitor@example.com', kind='enquiry').exists())


class PageRenderingTests(TestCase):
    """Every important route renders for the right role, with its controls."""

    def test_pages_render_for_each_role(self):
        public = ('home', 'branches', 'coaches', 'classes', 'plans', 'contact', 'class_list', 'login', 'register')
        for page in public:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(reverse(f'myfit:{page}')).status_code, 200)

        client_user = User.objects.get(username='demo_client1')
        self.client.force_login(client_user)
        for page in ('client_dashboard', 'client_bookings', 'client_membership', 'workouts', 'progress',
                     'client_attendance_history', 'notification_list', 'membership_pass', 'edit_profile',
                     'password_change', 'support_ticket_list', 'create_support_ticket', 'class_list',
                     'coaching_workouts', 'coaching_progress', 'coaching_trial'):
            with self.subTest(role='client', page=page):
                self.assertEqual(self.client.get(reverse(f'myfit:{page}')).status_code, 200)

        coach_user = User.objects.get(username='demo_maya')
        self.client.force_login(coach_user)
        for page in ('coach_dashboard', 'coach_clients', 'manage_classes', 'class_session_add',
                     'coaching_clients', 'notification_list', 'edit_profile'):
            with self.subTest(role='coach', page=page):
                self.assertEqual(self.client.get(reverse(f'myfit:{page}')).status_code, 200)
        assigned = CoachClientAssignment.objects.filter(coach__user=coach_user).first()
        self.assertEqual(self.client.get(reverse('myfit:coaching_client_records',
                                                 args=[assigned.client_id])).status_code, 200)
        dashboard = self.client.get(reverse('myfit:coach_dashboard'))
        self.assertContains(dashboard, 'Strength Foundations')

        self.client.force_login(User.objects.get(username='myfit_admin'))
        controls = {
            'manage_branches': ('branchSearch', 'branchStatusFilter', 'window.print()', 'branchModal'),
            'manage_coaches': ('coachSearch', 'coachStatusFilter', 'window.print()', 'coachModal'),
            'manage_members': ('memberSearch', 'memberStatusFilter', 'window.print()', 'memberModal'),
            'manage_classes': ('classSearch', 'classStatusFilter', 'window.print()', 'Publish', 'Cancel class'),
        }
        for page, needles in controls.items():
            response = self.client.get(reverse(f'myfit:{page}'))
            for needle in needles:
                with self.subTest(page=page, control=needle):
                    self.assertContains(response, needle)
        for page in ('admin_dashboard', 'manage_bookings', 'manage_plans', 'assign_client_membership',
                     'membership_requests', 'attendance_dashboard', 'membership_scanner', 'support_manage',
                     'specialty_manage', 'coaching_assignments', 'class_session_add', 'branch_add',
                     'coach_add', 'member_add', 'manage_payments'):
            with self.subTest(role='admin', page=page):
                self.assertEqual(self.client.get(reverse(f'myfit:{page}')).status_code, 200)

    def test_public_counts_are_dynamic(self):
        response = self.client.get(reverse('myfit:branches'))
        self.assertEqual(response.context['open_branch_count'], 3)
        self.assertEqual(response.context['coming_soon_count'], 1)
        self.assertContains(self.client.get(reverse('myfit:home')), 'COMING SOON')
        self.assertEqual(self.client.get(reverse('myfit:classes')).context['open_branch_count'], 3)
