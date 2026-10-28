import re
from datetime import timedelta
from time import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
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
from .models import MembershipPass, Notification, SupportTicket, SupportTicketMessage



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

class SupportAndNotificationTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user("alice", password="pass12345")
        self.other_user = User.objects.create_user("bob", password="pass12345")
        self.staff = User.objects.create_user("admin1", password="pass12345", is_staff=True)
        self.ticket = SupportTicket.objects.create(
            client=self.client_user, subject="Help", description="Broken"
        )

    def test_client_cannot_view_other_clients_ticket(self):
        self.client.login(username="bob", password="pass12345")
        r = self.client.get(reverse("myfit:support_ticket_detail", args=[self.ticket.pk]))
        self.assertEqual(r.status_code, 403)

    def test_client_cannot_see_internal_messages(self):
        SupportTicketMessage.objects.create(
            ticket=self.ticket, sender=self.staff, message="secret", is_internal=True
        )
        self.client.login(username="alice", password="pass12345")
        r = self.client.get(reverse("myfit:support_ticket_detail", args=[self.ticket.pk]))
        self.assertNotContains(r, "secret")

    def test_client_cannot_update_ticket(self):
        self.client.login(username="alice", password="pass12345")
        self.client.post(
            reverse("myfit:update_support_ticket", args=[self.ticket.pk]),
            {"status": "closed", "priority": "low"},
        )
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "open")

    def test_staff_update_notifies_client(self):
        self.client.login(username="admin1", password="pass12345")
        self.client.post(
            reverse("myfit:update_support_ticket", args=[self.ticket.pk]),
            {"status": "resolved", "priority": "normal"},
        )
        self.assertTrue(
            Notification.objects.filter(user=self.client_user).exists()
        )

    def test_cannot_mark_other_users_notification_read(self):
        n = Notification.objects.create(user=self.client_user, title="t", message="m")
        self.client.login(username="bob", password="pass12345")
        r = self.client.post(reverse("myfit:mark_notification_read", args=[n.pk]))
        self.assertEqual(r.status_code, 404)