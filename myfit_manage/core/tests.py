import re
from datetime import timedelta
from time import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core import signing
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .membership_tokens import (
    MEMBERSHIP_QR_MAX_AGE,
    MEMBERSHIP_QR_SALT,
    create_membership_verification_token,
)
from .models import MembershipPass


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
