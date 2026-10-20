import re
from datetime import date, timedelta
from time import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core import signing
from django.test import TestCase
from django.urls import reverse

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
        self.pass_record.expiry_date = date.today() + timedelta(days=1)
        self.assertEqual(self.pass_record.current_status, MembershipPass.Status.ACTIVE)

        self.pass_record.expiry_date = date.today() - timedelta(days=1)
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
