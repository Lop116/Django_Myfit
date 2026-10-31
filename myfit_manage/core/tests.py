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

from .forms import MembershipPlanForm
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


class MembershipPlanFormTests(TestCase):
    def test_allows_classes_saves_both_values_and_seeded_plan_values(self):
        form_data = {
            'name': 'Editable Class Plan',
            'price': '75.00',
            'duration_days': '30',
            'benefits': '',
            'allows_classes': 'on',
            'is_active': 'on',
        }
        form = MembershipPlanForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        plan = form.save()
        self.assertTrue(plan.allows_classes)

        form_data['allows_classes'] = ''
        form = MembershipPlanForm(data=form_data, instance=plan)
        self.assertTrue(form.is_valid(), form.errors)
        plan = form.save()
        self.assertFalse(plan.allows_classes)

        expected_seeded_values = {
            'My Access': False,
            'My Access XL': True,
            'My Access Premium': True,
        }
        for name, allows_classes in expected_seeded_values.items():
            with self.subTest(plan=name):
                self.assertEqual(
                    MembershipPlan.objects.get(name=name).allows_classes,
                    allows_classes,
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
        self.plan = MembershipPlan.objects.create(
            name='My Actual Dynamic Plan',
            price='75.00',
            duration_days=30,
        )
        today = timezone.localdate()
        self.client_membership = ClientMembership.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=24),
            agreed_price='70.00',
            status='active',
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
        self.assertContains(response, 'My Actual Dynamic Plan')
        self.assertNotContains(response, 'My Access XL')
        self.assertNotContains(response, 'My Access Premium')
        self.pass_record.refresh_from_db()
        self.assertEqual(self.pass_record.plan, MembershipPass.Plan.NEUTRAL)
        self.assertEqual(self.pass_record.status, MembershipPass.Status.ACTIVE)
        self.assertEqual(self.pass_record.expiry_date, self.client_membership.end_date)

    # Developer: Deshrao Saccaram
    def test_member_with_current_membership_gets_pass_provisioned(self):
        self.pass_record.delete()
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:membership_pass'))

        self.assertContains(response, 'My Actual Dynamic Plan')
        self.assertContains(response, 'Time-limited QR code')
        self.assertTrue(MembershipPass.objects.filter(user=self.user).exists())

    def test_existing_pass_is_synchronized_idempotently(self):
        self.pass_record.status = MembershipPass.Status.PENDING
        self.pass_record.expiry_date = None
        self.pass_record.save(update_fields=('status', 'expiry_date'))
        self.client.force_login(self.user)

        first_response = self.client.get(reverse('myfit:membership_pass'))
        self.pass_record.refresh_from_db()
        first_updated_at = self.pass_record.created_at
        first_id = self.pass_record.membership_id
        second_response = self.client.get(reverse('myfit:membership_pass'))
        self.pass_record.refresh_from_db()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(MembershipPass.objects.filter(user=self.user).count(), 1)
        self.assertEqual(self.pass_record.membership_id, first_id)
        self.assertEqual(self.pass_record.created_at, first_updated_at)
        self.assertEqual(self.pass_record.plan, MembershipPass.Plan.NEUTRAL)
        self.assertEqual(self.pass_record.status, MembershipPass.Status.ACTIVE)
        self.assertEqual(self.pass_record.expiry_date, self.client_membership.end_date)

    def test_no_or_ineligible_membership_does_not_provision_or_show_qr(self):
        self.pass_record.delete()
        self.client_membership.delete()
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:membership_pass'))

        self.assertContains(response, 'No eligible membership pass is available')
        self.assertNotContains(response, 'Time-limited QR code')
        self.assertFalse(MembershipPass.objects.filter(user=self.user).exists())

    def test_existing_active_pass_is_not_displayed_without_eligible_membership(self):
        self.client_membership.delete()
        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = timezone.localdate() + timedelta(days=1)
        self.pass_record.save(update_fields=('status', 'expiry_date'))
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:membership_pass'))

        self.assertContains(response, 'No eligible membership pass is available')
        self.assertNotContains(response, 'Time-limited QR code')
        self.assertTrue(MembershipPass.objects.filter(user=self.user).exists())

    def test_scheduled_expired_and_suspended_memberships_do_not_provision_pass(self):
        today = timezone.localdate()
        cases = (
            {
                'start_date': today + timedelta(days=1),
                'end_date': today + timedelta(days=30),
                'status': 'scheduled',
            },
            {
                'start_date': today - timedelta(days=30),
                'end_date': today - timedelta(days=1),
                'status': 'active',
            },
            {
                'start_date': today - timedelta(days=1),
                'end_date': today + timedelta(days=20),
                'status': 'suspended',
            },
            {
                'start_date': today - timedelta(days=1),
                'end_date': today + timedelta(days=20),
                'status': 'expired',
            },
        )
        self.client_membership.delete()
        self.pass_record.delete()
        self.client.force_login(self.user)

        for case in cases:
            with self.subTest(status=case['status'], start=case['start_date']):
                self.client_membership = ClientMembership.objects.create(
                    user=self.user,
                    plan=self.plan,
                    agreed_price='70.00',
                    **case,
                )
                if case['status'] == 'expired':
                    self.assertEqual(self.client_membership.current_status, 'expired')
                response = self.client.get(reverse('myfit:membership_pass'))
                self.assertContains(response, 'No eligible membership pass is available')
                self.assertNotContains(response, 'Time-limited QR code')
                self.assertFalse(MembershipPass.objects.filter(user=self.user).exists())
                self.client_membership.delete()

    def test_pass_eligibility_follows_scheduled_start_and_expiration_dates(self):
        start_date = timezone.localdate() + timedelta(days=1)
        end_date = start_date + timedelta(days=2)
        self.client_membership.start_date = start_date
        self.client_membership.end_date = end_date
        self.client_membership.status = 'scheduled'
        self.client_membership.save(
            update_fields=('start_date', 'end_date', 'status')
        )
        self.client.force_login(self.user)

        before_start = self.client.get(reverse('myfit:membership_pass'))

        self.assertEqual(self.client_membership.current_status, 'scheduled')
        self.assertContains(before_start, 'No eligible membership pass is available')
        self.assertNotContains(before_start, 'Time-limited QR code')

        with patch('django.utils.timezone.localdate', return_value=start_date):
            on_start = self.client.get(reverse('myfit:membership_pass'))
            self.assertEqual(self.client_membership.current_status, 'active')
        self.assertContains(on_start, 'Time-limited QR code')

        with patch(
            'django.utils.timezone.localdate',
            return_value=end_date + timedelta(days=1),
        ):
            after_expiration = self.client.get(reverse('myfit:membership_pass'))
            self.assertEqual(self.client_membership.current_status, 'expired')
        self.assertContains(
            after_expiration,
            'No eligible membership pass is available',
        )
        self.assertNotContains(after_expiration, 'Time-limited QR code')

    def test_ambiguous_active_memberships_do_not_provision_or_show_pass(self):
        self.pass_record.delete()
        second_membership = ClientMembership.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=self.client_membership.start_date,
            end_date=self.client_membership.end_date,
            agreed_price='70.00',
            status='active',
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:membership_pass'))

        self.assertContains(response, 'Multiple valid memberships were found')
        self.assertNotContains(response, 'Time-limited QR code')
        self.assertFalse(MembershipPass.objects.filter(user=self.user).exists())
        second_membership.delete()

    def test_status_reflects_pending_active_and_expired_records(self):
        self.assertEqual(self.pass_record.current_status, MembershipPass.Status.PENDING)

        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = timezone.localdate() + timedelta(days=1)
        self.assertEqual(self.pass_record.current_status, MembershipPass.Status.ACTIVE)

        self.pass_record.expiry_date = timezone.localdate() - timedelta(days=1)
        self.assertEqual(self.pass_record.current_status, MembershipPass.Status.EXPIRED)

    def test_qr_contains_only_opaque_signed_verification_data(self):
        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = self.client_membership.end_date
        self.pass_record.save(update_fields=('status', 'expiry_date'))
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
        self.pass_record.expiry_date = self.client_membership.end_date
        self.pass_record.save(update_fields=('status', 'expiry_date'))
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
        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = self.client_membership.end_date
        self.pass_record.save(update_fields=('status', 'expiry_date'))
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

    def test_existing_qr_token_cannot_render_after_membership_is_suspended(self):
        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = self.client_membership.end_date
        self.pass_record.save(update_fields=('status', 'expiry_date'))
        token = create_membership_verification_token(self.pass_record)
        self.client_membership.status = 'suspended'
        self.client_membership.save(update_fields=('status',))
        self.client.force_login(self.user)

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
        self.check_in_url = reverse('myfit:membership_qr_check_in')

    def authorize_staff(self, can_check_in=False):
        staff_user = get_user_model().objects.create_user(
            username='authorized-staff',
            password='StaffPassword!42',
            is_staff=True,
        )
        permissions = Permission.objects.filter(
            content_type__app_label='core',
            codename__in=(
                ('view_membershippass', 'add_attendancevisit')
                if can_check_in else ('view_membershippass',)
            ),
        )
        staff_user.user_permissions.add(*permissions)
        self.client.force_login(staff_user)
        return staff_user

    def create_active_pass(self):
        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = timezone.localdate() + timedelta(days=1)
        self.pass_record.save(update_fields=('status', 'expiry_date'))
        return create_membership_verification_token(self.pass_record)

    def create_client_membership(self, **overrides):
        today = timezone.localdate()
        plan = MembershipPlan.objects.create(
            name=f'Scanner Plan {ClientMembership.objects.count()}',
            price='50.00',
            duration_days=30,
        )
        values = {
            'user': self.user,
            'plan': plan,
            'start_date': today - timedelta(days=1),
            'end_date': today + timedelta(days=10),
            'agreed_price': '50.00',
            'status': 'active',
        }
        values.update(overrides)
        return ClientMembership.objects.create(**values)

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

        self.create_client_membership()
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
    def test_qr_scan_offers_explicit_check_in_but_does_not_create_visit(self):
        token = self.create_active_pass()
        self.create_client_membership()
        self.authorize_staff(can_check_in=True)

        response = self.verify_token(token)

        self.assertContains(response, 'VALID MEMBERSHIP')
        self.assertContains(response, 'CHECK IN CLIENT')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_scanner_does_not_offer_check_in_without_add_permission(self):
        token = self.create_active_pass()
        self.create_client_membership()
        self.authorize_staff()

        response = self.verify_token(token)

        self.assertContains(response, 'VALID MEMBERSHIP')
        self.assertNotContains(response, 'CHECK IN CLIENT')
        self.assertContains(response, 'not permitted to check in clients')

    def test_successful_qr_check_in_uses_pass_owner_and_generic_confirmation(self):
        token = self.create_active_pass()
        membership = self.create_client_membership()
        self.authorize_staff(can_check_in=True)

        scan_response = self.verify_token(token)
        self.assertContains(scan_response, 'CHECK IN CLIENT')
        self.assertFalse(AttendanceVisit.objects.exists())

        response = self.client.post(
            self.check_in_url,
            {'token': token},
            follow=True,
        )

        self.assertEqual(response.redirect_chain[0][0], self.scanner_url)
        visit = AttendanceVisit.objects.get()
        self.assertEqual(visit.membership, membership)
        self.assertIsNone(visit.check_out)
        self.assertContains(response, 'Client check-in recorded successfully.')
        self.assertNotContains(response, self.user.username)

    def test_duplicate_qr_check_in_creates_only_one_open_visit(self):
        token = self.create_active_pass()
        self.create_client_membership()
        self.authorize_staff(can_check_in=True)

        self.client.post(self.check_in_url, {'token': token})
        response = self.client.post(
            self.check_in_url,
            {'token': token},
            follow=True,
        )

        self.assertEqual(response.redirect_chain[0][0], self.scanner_url)
        self.assertEqual(AttendanceVisit.objects.count(), 1)
        self.assertContains(response, 'already checked in')

    def test_invalid_and_expired_qr_tokens_cannot_check_in(self):
        self.create_client_membership()
        token = self.create_active_pass()
        self.authorize_staff(can_check_in=True)

        invalid_response = self.client.post(
            self.check_in_url,
            {'token': 'not-a-valid-token'},
            follow=True,
        )
        self.assertEqual(invalid_response.redirect_chain[0][0], self.scanner_url)
        self.assertFalse(AttendanceVisit.objects.exists())
        self.assertContains(
            invalid_response,
            'QR token is invalid',
        )

        with patch(
            'django.core.signing.time.time',
            return_value=time() + MEMBERSHIP_QR_MAX_AGE + 1,
        ):
            expired_response = self.client.post(
                self.check_in_url,
                {'token': token},
                follow=True,
            )
        self.assertEqual(expired_response.redirect_chain[0][0], self.scanner_url)
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_inactive_or_expired_pass_cannot_check_in(self):
        membership = self.create_client_membership()
        self.authorize_staff(can_check_in=True)

        pending_token = create_membership_verification_token(self.pass_record)
        pending_response = self.client.post(
            self.check_in_url,
            {'token': pending_token},
        )
        self.assertRedirects(pending_response, self.scanner_url)
        self.assertFalse(AttendanceVisit.objects.exists())

        self.pass_record.status = MembershipPass.Status.ACTIVE
        self.pass_record.expiry_date = timezone.localdate() - timedelta(days=1)
        self.pass_record.save(update_fields=('status', 'expiry_date'))
        expired_token = create_membership_verification_token(self.pass_record)
        expired_response = self.client.post(
            self.check_in_url,
            {'token': expired_token},
        )
        self.assertRedirects(expired_response, self.scanner_url)
        self.assertFalse(AttendanceVisit.objects.filter(membership=membership).exists())

    def test_missing_client_membership_cannot_check_in(self):
        token = self.create_active_pass()
        self.authorize_staff(can_check_in=True)

        response = self.client.post(
            self.check_in_url,
            {'token': token},
            follow=True,
        )

        self.assertEqual(response.redirect_chain[0][0], self.scanner_url)
        self.assertFalse(AttendanceVisit.objects.exists())
        self.assertContains(
            response,
            'No currently valid client membership',
        )

    def test_expired_or_suspended_client_membership_cannot_check_in(self):
        token = self.create_active_pass()
        today = timezone.localdate()
        self.create_client_membership(
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),
            status='active',
        )
        self.create_client_membership(status='suspended')
        self.authorize_staff(can_check_in=True)

        response = self.client.post(self.check_in_url, {'token': token})

        self.assertRedirects(response, self.scanner_url)
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_future_scheduled_membership_cannot_check_in(self):
        token = self.create_active_pass()
        today = timezone.localdate()
        self.create_client_membership(
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=30),
            status='scheduled',
        )
        self.authorize_staff(can_check_in=True)

        response = self.client.post(self.check_in_url, {'token': token})

        self.assertRedirects(response, self.scanner_url)
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_scheduled_membership_is_eligible_on_its_start_date(self):
        token = self.create_active_pass()
        today = timezone.localdate()
        membership = self.create_client_membership(
            start_date=today,
            end_date=today + timedelta(days=10),
            status='scheduled',
        )
        self.authorize_staff(can_check_in=True)

        scan_response = self.verify_token(token)
        check_in_response = self.client.post(
            self.check_in_url,
            {'token': token},
        )

        self.assertContains(scan_response, 'CHECK IN CLIENT')
        self.assertRedirects(check_in_response, self.scanner_url)
        self.assertEqual(AttendanceVisit.objects.get().membership, membership)

    def test_multiple_eligible_memberships_fail_closed(self):
        token = self.create_active_pass()
        self.create_client_membership()
        self.create_client_membership()
        self.authorize_staff(can_check_in=True)

        scan_response = self.verify_token(token)
        check_in_response = self.client.post(
            self.check_in_url,
            {'token': token},
        )

        self.assertContains(scan_response, 'Multiple valid memberships were found')
        self.assertNotContains(scan_response, 'CHECK IN CLIENT')
        self.assertRedirects(check_in_response, self.scanner_url)
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_check_in_requires_staff_and_add_attendance_permission(self):
        token = self.create_active_pass()
        self.create_client_membership()

        ordinary_user = get_user_model().objects.create_user(
            username='ordinary-checkin-user',
            password='MemberPassword!42',
        )
        self.client.force_login(ordinary_user)
        self.assertEqual(
            self.client.post(self.check_in_url, {'token': token}).status_code,
            403,
        )

        staff_user = get_user_model().objects.create_user(
            username='scanner-without-attendance-permission',
            password='StaffPassword!42',
            is_staff=True,
        )
        staff_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='core',
                codename='view_membershippass',
            )
        )
        self.client.force_login(staff_user)
        self.assertEqual(
            self.client.post(self.check_in_url, {'token': token}).status_code,
            403,
        )
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_check_in_route_rejects_get_and_enforces_csrf(self):
        token = self.create_active_pass()
        self.create_client_membership()
        staff_user = self.authorize_staff(can_check_in=True)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(staff_user)

        self.assertEqual(self.client.get(self.check_in_url).status_code, 405)
        self.assertEqual(
            csrf_client.post(self.check_in_url, {'token': token}).status_code,
            403,
        )
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_public_verification_remains_read_only_for_attendance(self):
        token = self.create_active_pass()
        self.create_client_membership()

        response = self.client.get(
            reverse('myfit:membership_verify'),
            {'token': token},
        )

        self.assertContains(response, 'Membership status: Active')
        self.assertFalse(AttendanceVisit.objects.exists())

    def test_active_legacy_pass_without_active_subscription_is_not_verified_as_active(self):
        token = self.create_active_pass()
        self.authorize_staff()

        scanner_response = self.verify_token(token)
        public_response = self.client.get(
            reverse('myfit:membership_verify'),
            {'token': token},
        )

        self.assertContains(scanner_response, 'INACTIVE MEMBERSHIP')
        self.assertNotContains(scanner_response, 'CHECK IN CLIENT')
        self.assertContains(public_response, 'No currently active membership')
        self.assertNotContains(public_response, 'Membership status: Active')
        self.assertFalse(AttendanceVisit.objects.exists())


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

    # Developer: Deshrao Saccaram
    def assert_authenticated_navigation(self, response):
        self.assertContains(response, reverse('myfit:membership_pass'))
        self.assertContains(response, 'Membership QR Pass')
        self.assertContains(response, 'My Membership')
        self.assertContains(response, reverse('myfit:client_membership'))
        self.assertContains(response, 'Attendance History')
        self.assertContains(response, reverse('myfit:client_attendance_history'))
        self.assertNotContains(response, 'Staff QR Scanner')
        self.assertNotContains(response, 'Attendance Dashboard')
        self.assertNotContains(response, 'Membership Management')
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

    # Developer: Deshrao Saccaram
    def test_membership_navigation_is_available_on_classes_page_for_clients(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:classes'))

        self.assertContains(response, 'Membership QR Pass')
        self.assertContains(response, 'My Membership')
        self.assertContains(response, reverse('myfit:client_membership'))
        self.assertContains(response, 'Attendance History')
        self.assertContains(response, reverse('myfit:client_attendance_history'))

    # Developer: Deshrao Saccaram
    def test_authenticated_desktop_navigation_has_single_pass_and_logout(self):
        self.client.force_login(self.user)

        for page_name in ('home', 'login', 'register'):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(f'myfit:{page_name}'))
                content = response.content.decode()
                desktop_header = content.split(
                    '<header class="site-header"',
                    1,
                )[1].split('<details class="mobile-menu"', 1)[0]

                self.assertEqual(
                    desktop_header.count(
                        f'href="{reverse("myfit:membership_pass")}"',
                    ),
                    1,
                )
                self.assertEqual(
                    desktop_header.count(
                        f'action="{reverse("myfit:logout")}"',
                    ),
                    1,
                )
                self.assertEqual(desktop_header.count('>Log out</button>'), 1)
                self.assertEqual(
                    desktop_header.count('>Membership QR Pass</a>'),
                    1,
                )
                self.assertContains(response, 'mobile-menu')
                self.assertContains(response, 'notification-menu')

    # Developer: Deshrao Saccaram
    def test_authenticated_login_page_hides_login_form(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "YOU'RE SIGNED IN")
        self.assertContains(response, 'CONTINUE TO MYFIT')
        self.assertNotContains(response, 'id="id_password"')
        self.assertNotContains(response, 'Forgot Password?')

    # Developer: Deshrao Saccaram
    def test_guest_desktop_navigation_shows_login_without_member_controls(self):
        for page_name in ('home', 'login', 'register'):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(f'myfit:{page_name}'))
                content = response.content.decode()
                desktop_header = content.split(
                    '<header class="site-header"',
                    1,
                )[1].split('<details class="mobile-menu"', 1)[0]

                self.assertIn(
                    f'href="{reverse("myfit:login")}"',
                    desktop_header,
                )
                self.assertNotIn(
                    f'href="{reverse("myfit:membership_pass")}"',
                    desktop_header,
                )
                self.assertNotIn(
                    f'action="{reverse("myfit:logout")}"',
                    desktop_header,
                )

    # Developer: Deshrao Saccaram
    def test_authenticated_registration_page_hides_registration_form(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('myfit:register'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "YOU'RE SIGNED IN")
        self.assertContains(response, 'CONTINUE TO MYFIT')
        self.assertNotContains(response, 'id="id_password1"')
        self.assertNotContains(response, 'id="id_password2"')
        self.assertNotContains(response, 'CREATE MY ACCOUNT')

    # Developer: Deshrao Saccaram
    def test_guest_registration_preserves_selected_plan_query(self):
        response = self.client.get(
            reverse('myfit:register'),
            {'plan': 'access'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CREATE ACCOUNT')
        self.assertContains(response, 'id="id_password1"')
        self.assertContains(
            response,
            'action="{}?plan=access"'.format(reverse('myfit:register')),
        )

    # Developer: Deshrao Saccaram
    def test_staff_navigation_links_follow_route_permissions(self):
        staff_user = get_user_model().objects.create_user(
            username='membership-nav-staff',
            password='StaffPassword!42',
            is_staff=True,
        )
        permission_routes = {
            'add_clientmembership': (
                'Membership Management',
                'assign_client_membership',
            ),
            'view_attendancevisit': (
                'Attendance Dashboard',
                'attendance_dashboard',
            ),
            'view_membershippass': (
                'Staff QR Scanner',
                'membership_scanner',
            ),
        }

        for codename, (label, route_name) in permission_routes.items():
            with self.subTest(permission=codename):
                permission = Permission.objects.get(
                    content_type__app_label='core',
                    codename=codename,
                )
                staff_user.user_permissions.set((permission,))
                self.client.force_login(staff_user)

                response = self.client.get(reverse('myfit:home'))

                self.assertContains(response, label)
                self.assertContains(response, reverse(f'myfit:{route_name}'))
                for other_codename, (other_label, _) in permission_routes.items():
                    if other_codename != codename:
                        self.assertNotContains(response, other_label)
                self.assertNotContains(response, 'My Membership')
                self.assertNotContains(response, 'Attendance History')

    # Developer: Deshrao Saccaram
    def test_staff_without_tool_permissions_sees_no_staff_navigation(self):
        staff_user = get_user_model().objects.create_user(
            username='unprivileged-membership-nav-staff',
            password='StaffPassword!42',
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('myfit:home'))

        self.assertNotContains(response, 'MyFit Tools')
        self.assertNotContains(response, 'Membership Management')
        self.assertNotContains(response, 'Attendance Dashboard')
        self.assertNotContains(response, 'Staff QR Scanner')

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
