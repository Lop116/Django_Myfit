import re
from datetime import timedelta
from decimal import Decimal
from time import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core import signing
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .membership_tokens import (
    MEMBERSHIP_QR_MAX_AGE,
    MEMBERSHIP_QR_SALT,
    create_membership_verification_token,
)
from .models import (
    AttendanceVisit,
    ClientMembership,
    MembershipChangeRequest,
    MembershipPass,
    MembershipPlan,
    Notification,
)


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='myfit-member',
            email='member@example.com',
            password='OriginalSecurePass!42',
        )

    def test_reset_link_uses_secure_token_and_updates_password(self):
        response = self.client.post(
            reverse('myfit:password_reset'),
            {'email': self.user.email},
        )

        self.assertRedirects(response, reverse('myfit:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Reset your MyFit password', mail.outbox[0].subject)

        match = re.search(
            r'http://testserver/password-reset/confirm/([\w-]+)/([\w-]+)/',
            mail.outbox[0].body,
        )
        self.assertIsNotNone(match)
        uidb64, token = match.groups()

        response = self.client.get(
            reverse(
                'myfit:password_reset_confirm',
                kwargs={'uidb64': uidb64, 'token': token},
            )
        )
        self.assertRedirects(
            response,
            reverse(
                'myfit:password_reset_confirm',
                kwargs={'uidb64': uidb64, 'token': 'set-password'},
            ),
        )

        response = self.client.post(
            reverse(
                'myfit:password_reset_confirm',
                kwargs={'uidb64': uidb64, 'token': 'set-password'},
            ),
            {
                'new_password1': 'NewSecurePassword!59',
                'new_password2': 'NewSecurePassword!59',
            },
        )

        self.assertRedirects(response, reverse('myfit:password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewSecurePassword!59'))

    def test_login_page_links_to_password_reset(self):
        response = self.client.get(reverse('myfit:login'))

        self.assertContains(
            response,
            f'href="{reverse("myfit:password_reset")}"',
        )


class MembershipPassTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='pass-member',
            first_name='Amina',
            last_name='Rahman',
            email='amina@example.com',
            password='MemberPassword!42',
        )
        self.pass_record = MembershipPass.objects.create(
            user=self.user,
            plan=MembershipPass.Plan.ACCESS_XL,
        )

    def test_pass_requires_authentication(self):
        response = self.client.get(reverse('myfit:membership_pass'))

        self.assertRedirects(
            response,
            f'{reverse("myfit:login")}?next={reverse("myfit:membership_pass")}',
        )

    def test_member_sees_only_their_own_pass(self):
        other_user = get_user_model().objects.create_user(
            username='other-member',
            password='OtherPassword!42',
        )
        MembershipPass.objects.create(
            user=other_user,
            plan=MembershipPass.Plan.PREMIUM,
            status=MembershipPass.Status.ACTIVE,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:membership_pass'))

        self.assertContains(response, 'Amina Rahman')
        self.assertContains(response, 'My Access XL')
        self.assertNotContains(response, 'My Access Premium')

    def test_member_without_a_pass_does_not_get_one_created(self):
        self.pass_record.delete()
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:membership_pass'))

        self.assertContains(response, 'No membership pass is linked to your account')
        self.assertFalse(MembershipPass.objects.filter(user=self.user).exists())

    def test_status_reflects_pending_active_and_expired_records(self):
        self.assertEqual(self.pass_record.current_status, MembershipPass.Status.PENDING)

        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = timezone.localdate() + timedelta(days=1)
        self.assertEqual(self.pass_record.current_status, MembershipPass.Status.ACTIVE)

        self.pass_record.expiry_date = timezone.localdate() - timedelta(days=1)
        self.assertEqual(self.pass_record.current_status, MembershipPass.Status.EXPIRED)

    def test_qr_contains_only_opaque_signed_verification_data(self):
        token = create_membership_verification_token(self.pass_record)
        payload = signing.loads(token, salt=MEMBERSHIP_QR_SALT)

        self.assertEqual(
            payload,
            {
                'membership_id': str(self.pass_record.membership_id),
                'purpose': 'membership-verification',
            },
        )
        self.assertNotIn(self.user.email, token)
        self.assertNotIn(self.user.first_name, token)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('myfit:membership_qr'),
            {'token': token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')

    def test_verification_returns_status_without_personal_data(self):
        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.save()
        token = create_membership_verification_token(self.pass_record)

        response = self.client.get(
            reverse('myfit:membership_verify'),
            {'token': token},
        )

        self.assertContains(response, 'Membership status: Active')
        self.assertNotContains(response, self.user.email)
        self.assertNotContains(response, self.user.first_name)

    def test_invalid_and_expired_verification_tokens_are_rejected(self):
        invalid_response = self.client.get(
            reverse('myfit:membership_verify'),
            {'token': 'not-a-signed-token'},
        )
        self.assertEqual(invalid_response.status_code, 400)

        token = create_membership_verification_token(self.pass_record)
        with patch(
            'django.core.signing.time.time',
            return_value=time() + MEMBERSHIP_QR_MAX_AGE + 1,
        ):
            expired_response = self.client.get(
                reverse('myfit:membership_verify'),
                {'token': token},
            )
        self.assertEqual(expired_response.status_code, 400)

    def test_qr_image_requires_current_members_own_pass(self):
        token = create_membership_verification_token(self.pass_record)
        other_user = get_user_model().objects.create_user(
            username='different-member',
            password='DifferentPassword!42',
        )
        self.client.force_login(other_user)

        response = self.client.get(
            reverse('myfit:membership_qr'),
            {'token': token},
        )

        self.assertEqual(response.status_code, 404)


class MembershipScannerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='scanner-member',
            first_name='Amina',
            last_name='Rahman',
            email='scanner-member@example.com',
            password='MemberPassword!42',
        )
        self.pass_record = MembershipPass.objects.create(
            user=self.user,
            plan=MembershipPass.Plan.ACCESS,
        )
        self.scanner_url = reverse('myfit:membership_scanner')

    def authorize_staff(self):
        staff_user = get_user_model().objects.create_user(
            username='authorized-staff',
            password='StaffPassword!42',
            is_staff=True,
        )
        permission = Permission.objects.get(
            content_type__app_label='core',
            codename='view_membershippass',
        )
        staff_user.user_permissions.add(permission)
        self.client.force_login(staff_user)

    def test_scanner_requires_login_and_staff_permission(self):
        response = self.client.get(self.scanner_url)
        self.assertRedirects(
            response,
            f'{reverse("myfit:login")}?next={self.scanner_url}',
        )

        member_user = get_user_model().objects.create_user(
            username='ordinary-member',
            password='MemberPassword!42',
        )
        self.client.force_login(member_user)
        self.assertEqual(self.client.get(self.scanner_url).status_code, 403)

        staff_without_permission = get_user_model().objects.create_user(
            username='staff-without-permission',
            password='StaffPassword!42',
            is_staff=True,
        )
        self.client.force_login(staff_without_permission)
        self.assertEqual(self.client.get(self.scanner_url).status_code, 403)

    def test_authorized_staff_can_open_scanner(self):
        self.authorize_staff()

        response = self.client.get(self.scanner_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'START CAMERA SCANNER')
        self.assertContains(response, 'MANUAL VERIFICATION')
        self.assertContains(response, '/static/js/jsQR.js')
        self.assertContains(response, 'getUserMedia')
        self.assertContains(response, 'window.jsQR')
        self.assertContains(response, 'qr-frame-canvas')
        self.assertNotContains(response, 'BarcodeDetector')

    def verify_token(self, token):
        return self.client.post(
            self.scanner_url,
            {'verification_input': token},
        )

    def test_scanner_shows_valid_expired_and_inactive_memberships(self):
        self.authorize_staff()
        token = create_membership_verification_token(self.pass_record)

        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = timezone.localdate() + timedelta(days=1)
        self.pass_record.save()
        self.assertContains(self.verify_token(token), 'VALID MEMBERSHIP')

        self.pass_record.expiry_date = timezone.localdate() - timedelta(days=1)
        self.pass_record.save()
        self.assertContains(self.verify_token(token), 'EXPIRED MEMBERSHIP')

        self.pass_record.status = MembershipPass.Status.PENDING
        self.pass_record.expiry_date = None
        self.pass_record.save()
        self.assertContains(self.verify_token(token), 'INACTIVE MEMBERSHIP')

    def test_scanner_accepts_qr_verification_url(self):
        self.authorize_staff()
        token = create_membership_verification_token(self.pass_record)
        verification_url = (
            f'https://myfit.example{reverse("myfit:membership_verify")}?token={token}'
        )

        response = self.client.post(
            self.scanner_url,
            {'verification_input': verification_url},
        )

        self.assertContains(response, 'INACTIVE MEMBERSHIP')

    def test_scanner_distinguishes_invalid_and_expired_qr_tokens(self):
        self.authorize_staff()
        invalid_response = self.verify_token('not-a-valid-token')
        self.assertEqual(invalid_response.status_code, 400)
        self.assertContains(invalid_response, 'INVALID TOKEN', status_code=400)

        token = create_membership_verification_token(self.pass_record)
        with patch(
            'django.core.signing.time.time',
            return_value=time() + MEMBERSHIP_QR_MAX_AGE + 1,
        ):
            expired_response = self.verify_token(token)
        self.assertEqual(expired_response.status_code, 400)
        self.assertContains(expired_response, 'EXPIRED QR TOKEN', status_code=400)

    def test_scanner_results_do_not_reveal_member_information(self):
        self.authorize_staff()
        token = create_membership_verification_token(self.pass_record)

        response = self.verify_token(token)

        self.assertNotContains(response, self.user.email)
        self.assertNotContains(response, self.user.first_name)
        self.assertNotContains(response, str(self.pass_record.membership_id))


# Developer: Deshrao Saccaram
class MembershipChangeRequestTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.member = user_model.objects.create_user(
            username='change-request-member',
            password='MemberPassword!42',
        )
        self.other_member = user_model.objects.create_user(
            username='other-change-member',
            password='OtherPassword!42',
        )
        self.staff = user_model.objects.create_user(
            username='change-request-staff',
            password='StaffPassword!42',
            is_staff=True,
        )
        permission = Permission.objects.get(
            content_type__app_label='core',
            codename='change_membershipchangerequest',
        )
        self.staff.user_permissions.add(permission)

        self.current_plan = MembershipPlan.objects.create(
            name='Current Plan',
            price='50.00',
            duration_days=30,
        )
        self.requested_plan = MembershipPlan.objects.create(
            name='Requested Plan',
            price='80.00',
            duration_days=60,
        )
        self.other_plan = MembershipPlan.objects.create(
            name='Other Plan',
            price='95.00',
            duration_days=45,
        )
        today = timezone.localdate()
        self.membership = ClientMembership.objects.create(
            user=self.member,
            plan=self.current_plan,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=5),
            agreed_price=            Decimal('45.00'),
            status='active',
        )
        self.request_url = reverse('myfit:submit_membership_change_request')
        self.staff_url = reverse('myfit:membership_requests')

    def create_request(self, membership=None, requested_plan=None):
        return MembershipChangeRequest.objects.create(
            membership=membership or self.membership,
            requested_plan=requested_plan or self.requested_plan,
            reason='Please change my plan.',
        )

    def submit_request(self, plan=None, extra_data=None):
        data = {
            'requested_plan': (plan or self.requested_plan).pk,
            'reason': 'Please change my plan.',
        }
        if extra_data:
            data.update(extra_data)
        return self.client.post(self.request_url, data)

    def authorize_staff(self):
        self.client.force_login(self.staff)

    def review_request(self, change_request, decision='approve'):
        return self.client.post(
            reverse(
                'myfit:review_membership_change_request',
                kwargs={
                    'request_id': change_request.pk,
                    'decision': decision,
                },
            )
        )

    def test_request_submission_requires_login(self):
        response = self.submit_request()
        self.assertRedirects(
            response,
            f'{reverse("myfit:login")}?next={self.request_url}',
        )

    def test_client_cannot_choose_another_clients_membership(self):
        self.client.force_login(self.member)
        other_membership = ClientMembership.objects.create(
            user=self.other_member,
            plan=self.current_plan,
            start_date=self.membership.start_date,
            end_date=self.membership.end_date,
            agreed_price='50.00',
            status='active',
        )

        response = self.submit_request(
            extra_data={'membership': other_membership.pk},
        )

        self.assertRedirects(response, reverse('myfit:client_membership'))
        change_request = MembershipChangeRequest.objects.get()
        self.assertEqual(change_request.membership, self.membership)

    def test_request_is_rejected_without_a_current_membership(self):
        self.client.force_login(self.other_member)

        response = self.submit_request()

        self.assertRedirects(response, reverse('myfit:client_membership'))
        self.assertFalse(MembershipChangeRequest.objects.exists())

    def test_client_can_create_pending_request_for_another_active_plan(self):
        self.client.force_login(self.member)

        response = self.submit_request(
            extra_data={'reason': ''},
        )

        self.assertRedirects(response, reverse('myfit:client_membership'))
        change_request = MembershipChangeRequest.objects.get()
        self.assertEqual(change_request.membership, self.membership)
        self.assertEqual(change_request.requested_plan, self.requested_plan)
        self.assertEqual(change_request.reason, '')
        self.assertEqual(change_request.status, 'pending')

    def test_membership_page_shows_request_status_history(self):
        self.create_request()
        self.client.force_login(self.member)

        response = self.client.get(reverse('myfit:client_membership'))

        self.assertContains(response, 'Plan Change Request History')
        self.assertContains(response, 'Requested Plan')
        self.assertContains(response, 'Pending')

    def test_same_plan_is_rejected_server_side(self):
        self.client.force_login(self.member)

        response = self.submit_request(plan=self.current_plan)

        self.assertRedirects(response, reverse('myfit:client_membership'))
        self.assertFalse(MembershipChangeRequest.objects.exists())

    def test_inactive_plan_is_rejected_server_side(self):
        self.requested_plan.is_active = False
        self.requested_plan.save(update_fields=('is_active',))
        self.client.force_login(self.member)

        response = self.submit_request()

        self.assertRedirects(response, reverse('myfit:client_membership'))
        self.assertFalse(MembershipChangeRequest.objects.exists())

    def test_duplicate_pending_request_is_prevented(self):
        self.client.force_login(self.member)
        existing = self.create_request()

        response = self.submit_request(plan=self.other_plan)

        self.assertRedirects(response, reverse('myfit:client_membership'))
        self.assertEqual(
            MembershipChangeRequest.objects.filter(
                membership=self.membership,
                status='pending',
            ).count(),
            1,
        )
        self.assertEqual(existing.requested_plan, self.requested_plan)

    def test_staff_views_and_actions_require_staff_permission(self):
        self.client.force_login(self.member)
        change_request = self.create_request()

        self.assertEqual(self.client.get(self.staff_url).status_code, 403)
        self.assertEqual(self.review_request(change_request).status_code, 403)

        staff_without_permission = get_user_model().objects.create_user(
            username='unprivileged-change-staff',
            password='StaffPassword!42',
            is_staff=True,
        )
        self.client.force_login(staff_without_permission)
        self.assertEqual(self.client.get(self.staff_url).status_code, 403)
        self.assertEqual(self.review_request(change_request).status_code, 403)

    def test_staff_list_contains_only_pending_requests(self):
        self.create_request()
        reviewed = self.create_request(
            membership=ClientMembership.objects.create(
                user=self.other_member,
                plan=self.current_plan,
                start_date=self.membership.start_date,
                end_date=self.membership.end_date,
                agreed_price='50.00',
                status='active',
            ),
        )
        reviewed.status = 'rejected'
        reviewed.save(update_fields=('status',))
        self.authorize_staff()

        response = self.client.get(self.staff_url)

        self.assertContains(response, 'Requested Plan')
        self.assertContains(response, self.member.username)
        self.assertNotContains(response, self.other_member.username)

    def test_approval_creates_scheduled_membership_after_current_end(self):
        change_request = self.create_request()
        original_dates = (self.membership.start_date, self.membership.end_date)
        original_price = Decimal('45.00')
        self.authorize_staff()

        response = self.review_request(change_request)

        self.assertRedirects(response, self.staff_url)
        change_request.refresh_from_db()
        self.membership.refresh_from_db()
        new_membership = ClientMembership.objects.get(
            user=self.member,
            plan=self.requested_plan,
        )
        self.assertEqual(change_request.status, 'approved')
        self.assertEqual(change_request.reviewed_by, self.staff)
        self.assertIsNotNone(change_request.reviewed_at)
        self.assertEqual(
            (self.membership.start_date, self.membership.end_date),
            original_dates,
        )
        self.assertEqual(self.membership.agreed_price, original_price)
        self.assertEqual(
            new_membership.start_date,
            self.membership.end_date + timedelta(days=1),
        )
        self.assertEqual(
            new_membership.end_date,
            new_membership.start_date + timedelta(days=59),
        )
        self.assertEqual(new_membership.agreed_price, Decimal('80.00'))
        self.assertEqual(new_membership.status, 'scheduled')
        self.assertEqual(new_membership.current_status, 'scheduled')
        with patch(
            'django.utils.timezone.localdate',
            return_value=new_membership.start_date,
        ):
            self.assertEqual(new_membership.current_status, 'active')

    def test_approval_is_blocked_when_another_membership_overlaps(self):
        change_request = self.create_request()
        overlapping_start = self.membership.end_date + timedelta(days=2)
        conflict = ClientMembership.objects.create(
            user=self.member,
            plan=self.other_plan,
            start_date=overlapping_start,
            end_date=overlapping_start + timedelta(days=4),
            agreed_price=self.other_plan.price,
            status='scheduled',
        )
        self.authorize_staff()

        response = self.review_request(change_request)

        self.assertRedirects(response, self.staff_url)
        change_request.refresh_from_db()
        self.assertEqual(change_request.status, 'pending')
        self.assertEqual(
            ClientMembership.objects.filter(user=self.member).count(),
            2,
        )
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, 'scheduled')

    def test_rejection_records_reviewer_without_changing_membership(self):
        change_request = self.create_request()
        original = (
            self.membership.plan_id,
            self.membership.start_date,
            self.membership.end_date,
            Decimal('45.00'),
            self.membership.status,
        )
        self.authorize_staff()

        response = self.review_request(change_request, decision='reject')

        self.assertRedirects(response, self.staff_url)
        change_request.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(change_request.status, 'rejected')
        self.assertEqual(change_request.reviewed_by, self.staff)
        self.assertIsNotNone(change_request.reviewed_at)
        self.assertEqual(
            (
                self.membership.plan_id,
                self.membership.start_date,
                self.membership.end_date,
                self.membership.agreed_price,
                self.membership.status,
            ),
            original,
        )
        self.assertEqual(ClientMembership.objects.filter(user=self.member).count(), 1)

    def test_already_approved_request_cannot_be_processed_again(self):
        change_request = self.create_request()
        self.authorize_staff()
        self.review_request(change_request)
        change_request.refresh_from_db()
        reviewed_at = change_request.reviewed_at

        response = self.review_request(change_request)

        self.assertRedirects(response, self.staff_url)
        change_request.refresh_from_db()
        self.assertEqual(change_request.status, 'approved')
        self.assertEqual(change_request.reviewed_at, reviewed_at)
        self.assertEqual(ClientMembership.objects.filter(user=self.member).count(), 2)

    def test_staff_review_actions_require_post_and_csrf(self):
        change_request = self.create_request()
        self.authorize_staff()
        review_url = reverse(
            'myfit:review_membership_change_request',
            kwargs={'request_id': change_request.pk, 'decision': 'approve'},
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)

        self.assertEqual(csrf_client.get(review_url).status_code, 405)
        self.assertEqual(csrf_client.post(review_url).status_code, 403)


class AuthenticationPresentationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='amina-fit',
            first_name='Amina',
            last_name='Rahman',
            email='amina-fit@example.com',
            password='StrongFitPassword!8462',
        )

    def assert_authenticated_navigation(self, response):
        self.assertContains(response, 'Amina')
        self.assertContains(response, reverse('myfit:membership_pass'))
        self.assertGreaterEqual(
            response.content.count(reverse('myfit:logout').encode()),
            2,
        )
        self.assertGreaterEqual(response.content.count(b'Log out'), 2)

    def test_login_establishes_session_and_public_navigation_shows_member(self):
        response = self.client.post(
            reverse('myfit:login'),
            {
                'username': 'amina-fit',
                'password': 'StrongFitPassword!8462',
            },
        )

        self.assertRedirects(response, reverse('myfit:home'))
        self.assertEqual(
            self.client.session['_auth_user_id'],
            str(self.user.pk),
        )

        public_pages = (
            'home',
            'branches',
            'coaches',
            'contact',
            'plans',
            'login',
            'register',
        )
        for page_name in public_pages:
            with self.subTest(page=page_name):
                page_response = self.client.get(reverse(f'myfit:{page_name}'))
                self.assert_authenticated_navigation(page_response)

    def test_registration_logs_member_in_and_home_shows_account(self):
        response = self.client.post(
            reverse('myfit:register'),
            {
                'first_name': 'Maya',
                'last_name': 'Noor',
                'email': 'maya-noor@example.com',
                'username': 'maya-noor',
                'password1': 'AnotherStrongPassword!732',
                'password2': 'AnotherStrongPassword!732',
            },
        )

        self.assertRedirects(response, reverse('myfit:home'))
        registered_user = get_user_model().objects.get(username='maya-noor')
        self.assertEqual(
            self.client.session['_auth_user_id'],
            str(registered_user.pk),
        )
        self.assertContains(
            self.client.get(reverse('myfit:home')),
            'Hi, Maya',
        )

    def test_guest_navigation_has_login_and_registration_links(self):
        response = self.client.get(reverse('myfit:home'))

        self.assertContains(response, reverse('myfit:login'))
        self.assertContains(response, reverse('myfit:register'))
        login_response = self.client.get(reverse('myfit:login'))
        self.assertContains(login_response, 'Register for an account')
        self.assertContains(login_response, reverse('myfit:register'))

    def test_logout_uses_post_clears_session_and_redirects_home(self):
        self.client.force_login(self.user)

        get_response = self.client.get(reverse('myfit:logout'))
        self.assertEqual(get_response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

        response = self.client.post(reverse('myfit:logout'))

        self.assertRedirects(response, reverse('myfit:home'))
        self.assertNotIn('_auth_user_id', self.client.session)
        home_response = self.client.get(reverse('myfit:home'))
        self.assertContains(home_response, 'Log in')
        self.assertContains(home_response, 'JOIN MYFIT')
        self.assertNotContains(home_response, 'MYFIT PASS ·')


class NotificationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='notification-member',
            email='notification-member@example.com',
            password='NotificationPassword!42',
        )
        self.other_user = get_user_model().objects.create_user(
            username='other-notification-member',
            email='other-notification-member@example.com',
            password='OtherNotificationPassword!42',
        )
        self.read_all_url = reverse('myfit:notifications_read_all')

    def create_notification(self, user, title, **kwargs):
        return Notification.objects.create(
            user=user,
            title=title,
            message=f'Message for {title}',
            **kwargs,
        )

    def test_notification_actions_require_authentication_and_post(self):
        notification = self.create_notification(self.user, 'Private update')
        read_url = reverse(
            'myfit:notification_read',
            kwargs={'notification_id': notification.pk},
        )

        self.assertEqual(self.client.post(read_url).status_code, 302)
        self.assertEqual(self.client.post(self.read_all_url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(read_url).status_code, 405)
        self.assertEqual(self.client.get(self.read_all_url).status_code, 405)

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

    def test_members_can_only_mark_their_own_notification_as_read(self):
        notification = self.create_notification(self.user, 'My update')
        self.client.force_login(self.other_user)

        response = self.client.post(
            reverse(
                'myfit:notification_read',
                kwargs={'notification_id': notification.pk},
            )
        )

        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

    def test_marking_notification_read_sets_read_timestamp_and_redirects(self):
        notification = self.create_notification(self.user, 'My update')
        self.client.force_login(self.user)
        destination = reverse('myfit:plans')

        response = self.client.post(
            reverse(
                'myfit:notification_read',
                kwargs={'notification_id': notification.pk},
            ),
            {'next': destination},
        )

        self.assertRedirects(response, destination)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_read_action_enforces_csrf(self):
        notification = self.create_notification(self.user, 'CSRF protected')
        read_url = reverse(
            'myfit:notification_read',
            kwargs={'notification_id': notification.pk},
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        self.assertEqual(csrf_client.post(read_url).status_code, 403)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

        csrf_client.get(reverse('myfit:home'))
        csrf_token = csrf_client.cookies['csrftoken'].value
        response = csrf_client.post(
            read_url,
            {'csrfmiddlewaretoken': csrf_token},
        )

        self.assertEqual(response.status_code, 302)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_all_read_is_scoped_to_current_user(self):
        own_unread = self.create_notification(self.user, 'My unread')
        own_read = self.create_notification(
            self.user,
            'Already read',
            is_read=True,
            read_at=timezone.now(),
        )
        other_unread = self.create_notification(self.other_user, 'Other unread')
        self.client.force_login(self.user)

        response = self.client.post(
            self.read_all_url,
            {'next': reverse('myfit:plans')},
        )

        self.assertRedirects(response, reverse('myfit:plans'))
        own_unread.refresh_from_db()
        own_read.refresh_from_db()
        other_unread.refresh_from_db()
        self.assertTrue(own_unread.is_read)
        self.assertIsNotNone(own_unread.read_at)
        self.assertTrue(own_read.is_read)
        self.assertFalse(other_unread.is_read)
        self.assertIsNone(other_unread.read_at)

    def test_context_and_dropdown_show_unread_count_and_latest_ten_only(self):
        for number in range(12):
            self.create_notification(
                self.user,
                f'Member notice {number}',
                is_read=number < 2,
                read_at=timezone.now() if number < 2 else None,
            )
        self.create_notification(self.other_user, 'Another member secret')
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:home'))

        self.assertEqual(response.context['unread_notification_count'], 10)
        self.assertEqual(len(response.context['latest_notifications']), 10)
        self.assertContains(response, '10 unread')
        self.assertContains(response, 'Member notice 11')
        self.assertContains(response, 'Mark all as read')
        self.assertNotContains(response, 'Member notice 0')
        self.assertNotContains(response, 'Another member secret')
        self.assertEqual(response.content.count(b'class="notification-menu"'), 2)

    def test_dropdown_renders_on_all_public_and_auth_pages_for_members(self):
        self.client.force_login(self.user)
        for page_name in (
            'home',
            'branches',
            'coaches',
            'contact',
            'plans',
            'login',
            'register',
        ):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(f'myfit:{page_name}'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.content.count(b'class="notification-menu"'),
                    2,
                )

    def test_guest_does_not_see_notification_dropdown(self):
        response = self.client.get(reverse('myfit:home'))

        self.assertNotContains(response, 'notification-menu')
        self.assertEqual(response.context['unread_notification_count'], 0)


# ==========================================================
# TASK 2 - ATTENDANCE MANAGEMENT TESTS
# Developer: Deshrao Saccaram


class AttendanceManagementTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.member = user_model.objects.create_user(
            username='attendance-member',
            first_name='Jamie',
            last_name='Member',
            password='MemberPassword!42',
        )
        self.other_member = user_model.objects.create_user(
            username='private-attendance-member',
            password='OtherPassword!42',
        )
        self.staff = user_model.objects.create_user(
            username='attendance-staff',
            password='StaffPassword!42',
            is_staff=True,
        )
        self.staff.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label='core',
                codename__in=(
                    'view_attendancevisit',
                    'add_attendancevisit',
                    'change_attendancevisit',
                ),
            )
        )
        self.plan = MembershipPlan.objects.create(
            name='Attendance Plan',
            price='55.00',
            duration_days=30,
        )
        self.other_plan = MembershipPlan.objects.create(
            name='Private Attendance Plan',
            price='65.00',
            duration_days=30,
        )
        today = timezone.localdate()
        self.membership = ClientMembership.objects.create(
            user=self.member,
            plan=self.plan,
            start_date=today - timedelta(days=3),
            end_date=today + timedelta(days=3),
            agreed_price='55.00',
            status='active',
        )
        self.other_membership = ClientMembership.objects.create(
            user=self.other_member,
            plan=self.other_plan,
            start_date=today - timedelta(days=3),
            end_date=today + timedelta(days=3),
            agreed_price='65.00',
            status='active',
        )
        self.dashboard_url = reverse('myfit:attendance_dashboard')
        self.check_in_url = reverse('myfit:attendance_check_in')
        self.history_url = reverse('myfit:client_attendance_history')

    def authorize_staff(self):
        self.client.force_login(self.staff)

    def post_check_in(self, membership=None):
        return self.client.post(
            self.check_in_url,
            {'membership': (membership or self.membership).pk},
        )

    def post_check_out(self, visit):
        return self.client.post(
            reverse(
                'myfit:attendance_check_out',
                kwargs={'visit_id': visit.pk},
            )
        )

    def test_attendance_management_requires_staff_permissions(self):
        self.assertRedirects(
            self.client.get(self.dashboard_url),
            f'{reverse("myfit:login")}?next={self.dashboard_url}',
        )

        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.dashboard_url).status_code, 403)
        self.assertEqual(self.post_check_in().status_code, 403)
        visit = AttendanceVisit.objects.create(membership=self.membership)
        self.assertEqual(self.post_check_out(visit).status_code, 403)

        unprivileged_staff = get_user_model().objects.create_user(
            username='unprivileged-attendance-staff',
            password='StaffPassword!42',
            is_staff=True,
        )
        self.client.force_login(unprivileged_staff)
        self.assertEqual(self.client.get(self.dashboard_url).status_code, 403)
        self.assertEqual(self.post_check_in().status_code, 403)
        self.assertEqual(self.post_check_out(visit).status_code, 403)

    def test_staff_can_check_in_with_valid_membership(self):
        self.authorize_staff()

        response = self.post_check_in()

        self.assertRedirects(response, self.dashboard_url)
        visit = AttendanceVisit.objects.get(membership=self.membership)
        self.assertIsNone(visit.check_out)
        self.assertTrue(timezone.is_aware(visit.check_in))
        self.assertContains(
            self.client.get(self.dashboard_url),
            'Currently Checked In',
        )

    def test_duplicate_check_in_is_prevented(self):
        self.authorize_staff()
        self.post_check_in()

        response = self.post_check_in()

        self.assertRedirects(response, self.dashboard_url)
        self.assertEqual(
            AttendanceVisit.objects.filter(
                membership=self.membership,
                check_out__isnull=True,
            ).count(),
            1,
        )

    def test_staff_can_check_out_an_open_visit(self):
        visit = AttendanceVisit.objects.create(membership=self.membership)
        self.authorize_staff()

        response = self.post_check_out(visit)

        self.assertRedirects(response, self.dashboard_url)
        visit.refresh_from_db()
        self.assertIsNotNone(visit.check_out)
        self.assertTrue(timezone.is_aware(visit.check_out))
        self.assertGreaterEqual(visit.check_out, visit.check_in)

    def test_repeated_checkout_does_not_change_existing_checkout(self):
        visit = AttendanceVisit.objects.create(membership=self.membership)
        self.authorize_staff()
        self.post_check_out(visit)
        visit.refresh_from_db()
        original_checkout = visit.check_out

        response = self.post_check_out(visit)

        self.assertRedirects(response, self.dashboard_url)
        visit.refresh_from_db()
        self.assertEqual(visit.check_out, original_checkout)

    def test_checkout_before_checkin_time_is_rejected(self):
        visit = AttendanceVisit.objects.create(membership=self.membership)
        self.authorize_staff()
        with patch(
            'core.membership_services.timezone.now',
            return_value=visit.check_in - timedelta(seconds=1),
        ):
            response = self.post_check_out(visit)

        self.assertRedirects(response, self.dashboard_url)
        visit.refresh_from_db()
        self.assertIsNone(visit.check_out)

    def test_expired_membership_cannot_check_in(self):
        self.membership.end_date = timezone.localdate() - timedelta(days=1)
        self.membership.save(update_fields=('end_date',))
        self.authorize_staff()

        response = self.post_check_in()

        self.assertRedirects(response, self.dashboard_url)
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_suspended_membership_cannot_check_in(self):
        self.membership.status = 'suspended'
        self.membership.save(update_fields=('status',))
        self.authorize_staff()

        response = self.post_check_in()

        self.assertRedirects(response, self.dashboard_url)
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_future_scheduled_membership_cannot_check_in(self):
        self.membership.status = 'scheduled'
        self.membership.start_date = timezone.localdate() + timedelta(days=1)
        self.membership.end_date = timezone.localdate() + timedelta(days=30)
        self.membership.save(update_fields=('status', 'start_date', 'end_date'))
        self.authorize_staff()

        response = self.post_check_in()

        self.assertRedirects(response, self.dashboard_url)
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_scheduled_membership_is_valid_on_its_start_date(self):
        today = timezone.localdate()
        self.membership.status = 'scheduled'
        self.membership.start_date = today
        self.membership.end_date = today + timedelta(days=5)
        self.membership.save(update_fields=('status', 'start_date', 'end_date'))
        self.assertEqual(self.membership.current_status, 'active')
        self.authorize_staff()

        response = self.post_check_in()

        self.assertRedirects(response, self.dashboard_url)
        self.assertTrue(
            AttendanceVisit.objects.filter(
                membership=self.membership,
            ).exists()
        )

    def test_client_attendance_history_is_scoped_to_the_logged_in_user(self):
        AttendanceVisit.objects.create(membership=self.membership)
        AttendanceVisit.objects.create(membership=self.other_membership)
        self.client.force_login(self.member)

        response = self.client.get(self.history_url)

        self.assertContains(response, self.plan.name)
        self.assertNotContains(response, self.other_plan.name)
        self.assertEqual(
            list(response.context['attendance_history']),
            list(AttendanceVisit.objects.filter(membership=self.membership)),
        )

    def test_attendance_mutations_are_post_only_and_csrf_protected(self):
        visit = AttendanceVisit.objects.create(membership=self.membership)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        checkout_url = reverse(
            'myfit:attendance_check_out',
            kwargs={'visit_id': visit.pk},
        )

        self.assertEqual(csrf_client.get(self.check_in_url).status_code, 405)
        self.assertEqual(csrf_client.get(checkout_url).status_code, 405)
        self.assertEqual(csrf_client.post(self.check_in_url).status_code, 403)
        self.assertEqual(csrf_client.post(checkout_url).status_code, 403)
        self.assertEqual(AttendanceVisit.objects.count(), 1)


# END TASK 2 - ATTENDANCE MANAGEMENT TESTS
