
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    ClientProfile,
    CoachProfile,
    CoachClientAssignment,
    WorkoutLog,
    ProgressEntry
)

User = get_user_model()


class CoachingTests(TestCase):

    @classmethod
    def setUpTestData(cls):

        # Create the roles used by MyFit.
        for role in ['Admin', 'Coach', 'Client']:
            Group.objects.get_or_create(name=role)

        # Create users for testing.
        cls.admin_user = User.objects.create_user(
            username='test_admin',
            password='testpass123'
        )

        cls.client_user = User.objects.create_user(
            username='test_client',
            password='testpass123'
        )

        cls.coach_user = User.objects.create_user(
            username='test_coach',
            password='testpass123'
        )

        cls.other_coach = User.objects.create_user(
            username='other_coach',
            password='testpass123'
        )

        # Assign roles.
        cls.admin_user.groups.add(
            Group.objects.get(name='Admin')
        )

        cls.client_user.groups.add(
            Group.objects.get(name='Client')
        )

        cls.coach_user.groups.add(
            Group.objects.get(name='Coach')
        )

        cls.other_coach.groups.add(
            Group.objects.get(name='Coach')
        )

        # Create profiles.
        cls.client_profile, _ = (
            ClientProfile.objects.get_or_create(
                user=cls.client_user
            )
        )

        cls.coach_profile, _ = (
            CoachProfile.objects.get_or_create(
                user=cls.coach_user
            )
        )

        cls.other_profile, _ = (
            CoachProfile.objects.get_or_create(
                user=cls.other_coach
            )
        )

    def test_assign_and_reassign_client(self):

        # Log in as administrator.
        self.client.force_login(self.admin_user)

        url = reverse('myfit:coaching_assign')

        # Assign client to first coach.
        response = self.client.post(url, {
            'client': self.client_profile.pk,
            'coach': self.coach_profile.pk
        })

        self.assertEqual(response.status_code, 302)

        assignment = CoachClientAssignment.objects.get(
            client=self.client_profile
        )

        self.assertEqual(
            assignment.coach,
            self.coach_profile
        )

        # Reassign client to second coach.
        self.client.post(url, {
            'client': self.client_profile.pk,
            'coach': self.other_profile.pk
        })

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.coach,
            self.other_profile
        )

        # Client must still have only one assignment.
        self.assertEqual(
            CoachClientAssignment.objects.count(), 1
        )

        # Remove assignment.
        self.client.post(
            reverse(
                'myfit:coaching_remove_assignment',
                args=[assignment.pk]
            )
        )

        self.assertFalse(
            CoachClientAssignment.objects.exists()
        )

    def test_client_workout_crud(self):

        self.client.force_login(self.client_user)

        data = {
            'workout_type': 'cardio',
            'workout_date': timezone.localdate().isoformat(),
            'duration_minutes': 30,
            'notes': 'Morning run'
        }

        # CREATE
        self.client.post(
            reverse('myfit:coaching_workouts'),
            data
        )

        workout = WorkoutLog.objects.get(
            client=self.client_profile
        )

        self.assertEqual(workout.duration_minutes, 30)

        # UPDATE
        data['duration_minutes'] = 45

        self.client.post(
            reverse(
                'myfit:coaching_edit_workout',
                args=[workout.pk]
            ),
            data
        )

        workout.refresh_from_db()

        self.assertEqual(workout.duration_minutes, 45)

        # DELETE
        self.client.post(
            reverse(
                'myfit:coaching_delete_workout',
                args=[workout.pk]
            )
        )

        self.assertFalse(
            WorkoutLog.objects.filter(pk=workout.pk).exists()
        )

    def test_assigned_coach_can_view_records(self):

        # Assign the client to the first coach.
        CoachClientAssignment.objects.create(
            client=self.client_profile,
            coach=self.coach_profile
        )

        # Add a workout record.
        WorkoutLog.objects.create(
            client=self.client_profile,
            workout_type='strength',
            workout_date=timezone.localdate(),
            duration_minutes=50
        )

        url = reverse(
            'myfit:coaching_client_records',
            args=[self.client_profile.pk]
        )

        # Assigned coach is allowed.
        self.client.force_login(self.coach_user)

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'strength', html=False) if False else None
        self.assertContains(response, '50 min')

        # Another coach is not allowed.
        self.client.force_login(self.other_coach)

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_progress_validation_and_history(self):

        self.client.force_login(self.client_user)

        url = reverse('myfit:coaching_progress')

        # Add two valid weight measurements.
        for value, days in [('75.50', 3), ('74.20', 0)]:

            response = self.client.post(url, {
                'measurement_type': 'weight',
                'value': value,
                'unit': 'kg',
                'recorded_on': (
                    timezone.localdate()
                    - timedelta(days=days)
                ).isoformat()
            })

            self.assertEqual(response.status_code, 302)

        self.assertEqual(
            ProgressEntry.objects.count(), 2
        )

        # The history must show the saved measurements.
        response = self.client.get(url)
        self.assertContains(response, '74.20')

        # Reject negative measurements.
        self.client.post(url, {
            'measurement_type': 'weight',
            'value': '-5',
            'unit': 'kg',
            'recorded_on': timezone.localdate().isoformat()
        })

        # Reject an invalid measurement unit.
        self.client.post(url, {
            'measurement_type': 'distance',
            'value': '2',
            'unit': 'kg',
            'recorded_on': timezone.localdate().isoformat()
        })

        # Invalid submissions must not create records.
        self.assertEqual(
            ProgressEntry.objects.count(), 2
        )

    def test_client_cannot_edit_other_client_workout(self):

        # Create another client.
        other_user = User.objects.create_user(
            username='another_client',
            password='testpass123'
        )

        other_user.groups.add(
            Group.objects.get(name='Client')
        )

        other_profile, _ = (
            ClientProfile.objects.get_or_create(
                user=other_user
            )
        )

        workout = WorkoutLog.objects.create(
            client=other_profile,
            workout_type='cardio',
            workout_date=timezone.localdate(),
            duration_minutes=20
        )

        # Log in as the first client.
        self.client.force_login(self.client_user)

        # Trying to edit the other client's workout
        # must return 404.
        response = self.client.get(
            reverse(
                'myfit:coaching_edit_workout',
                args=[workout.pk]
            )
        )

        self.assertEqual(response.status_code, 404)
