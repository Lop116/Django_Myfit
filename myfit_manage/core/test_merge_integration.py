# Developer: Deshrao Saccaram
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import resolve, reverse

from . import admin_views, views
from .models import (
    AttendanceVisit,
    Branch,
    ClassBooking,
    ClassSession,
    ClientMembership,
    ClientProfile,
    CoachProfile,
    CoachSpecialty,
    MembershipChangeRequest,
    MembershipPass,
    MembershipPlan,
)


class MergedFeatureIntegrationTests(TestCase):
    def test_core_and_teammate_models_remain_registered_in_admin(self):
        models = (
            AttendanceVisit,
            Branch,
            ClassBooking,
            ClassSession,
            ClientMembership,
            ClientProfile,
            CoachProfile,
            CoachSpecialty,
            MembershipChangeRequest,
            MembershipPass,
            MembershipPlan,
        )

        for model in models:
            with self.subTest(model=model.__name__):
                self.assertTrue(admin.site.is_registered(model))

    def test_membership_and_teammate_routes_resolve_to_distinct_views(self):
        route_views = {
            'membership_pass': views.membership_pass,
            'membership_qr_check_in': views.membership_qr_check_in,
            'attendance_dashboard': views.attendance_dashboard,
            'class_list': views.class_list,
            'classes': views.classes,
            'admin_dashboard': admin_views.admin_dashboard,
        }

        for route_name, expected_view in route_views.items():
            with self.subTest(route=route_name):
                match = resolve(reverse(f'myfit:{route_name}'))
                self.assertIs(match.func, expected_view)

        self.assertEqual(resolve('/classes/').url_name, 'classes')
        self.assertEqual(resolve('/class-list/').url_name, 'class_list')

    def test_public_and_authenticated_feature_templates_render(self):
        public_pages = (
            'home',
            'branches',
            'coaches',
            'classes',
            'plans',
            'contact',
            'class_list',
            'login',
            'register',
        )

        for page_name in public_pages:
            with self.subTest(page=page_name):
                response = self.client.get(reverse(f'myfit:{page_name}'))
                self.assertEqual(response.status_code, 200)

        user = get_user_model().objects.create_user(
            username='merge-template-client',
            password='TestPassword!942',
        )
        self.client.force_login(user)

        for page_name in (
            'membership_pass',
            'client_membership',
            'client_attendance_history',
        ):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(f'myfit:{page_name}'))
                self.assertEqual(response.status_code, 200)

    def test_admin_dashboard_role_and_template_remain_available(self):
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        admin_user = get_user_model().objects.create_user(
            username='merge-dashboard-admin',
            password='TestPassword!942',
            is_staff=True,
        )
        admin_user.groups.add(admin_group)
        self.client.force_login(admin_user)

        response = self.client.get(reverse('myfit:admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin dashboard')

        class_response = self.client.get(reverse('myfit:manage_classes'))

        self.assertEqual(class_response.status_code, 200)
        self.assertContains(class_response, 'Manage Classes')
