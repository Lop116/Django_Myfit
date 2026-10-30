"""ADDED: regression tests for live administration and the one-time seed."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from .models import Branch, ClassSession, ClassBooking, ClientProfile, CoachProfile, MembershipPlan


class DynamicStarterDataTests(TestCase):
    def test_seed_rows_and_editable_image_fields_are_present(self):
        # Test DB migrations run before the tests; seed is in migration 0014.
        self.assertGreaterEqual(Branch.objects.count(), 4)
        self.assertGreaterEqual(CoachProfile.objects.count(), 4)
        self.assertGreaterEqual(ClientProfile.objects.count(), 2)
        self.assertGreaterEqual(ClassSession.objects.count(), 6)
        self.assertGreaterEqual(MembershipPlan.objects.count(), 3)
        self.assertGreaterEqual(ClassBooking.objects.filter(status='Confirmed').count(), 2)
        self.assertEqual(Branch.objects.get(name='Plaisance Mall').operational_status, 'Coming soon')
        self.assertTrue(Branch.objects.get(name='Trianon').image.name)

    def test_admin_can_hide_branch_and_public_directory_updates(self):
        user = get_user_model().objects.create_user(username='test-manager', password='StrongPass123!')
        group, _ = Group.objects.get_or_create(name='Admin')
        user.groups.add(group)
        self.client.force_login(user)
        branch = Branch.objects.get(name='Trianon')
        response = self.client.post(reverse('myfit:branch_toggle', args=[branch.pk]))
        self.assertEqual(response.status_code, 302)
        branch.refresh_from_db()
        self.assertFalse(branch.is_active)
        public = self.client.get(reverse('myfit:branches'))
        self.assertNotContains(public, 'Trianon')

    def test_admin_management_pages_have_live_counts(self):
        user = get_user_model().objects.create_user(username='test-admin-summary', password='StrongPass123!')
        user.groups.add(Group.objects.get_or_create(name='Admin')[0])
        self.client.force_login(user)
        for page in ('manage_branches', 'manage_coaches', 'manage_classes'):
            response = self.client.get(reverse('myfit:' + page))
            self.assertEqual(response.status_code, 200)
        self.assertContains(self.client.get(reverse('myfit:manage_classes')), 'Confirmed bookings')
