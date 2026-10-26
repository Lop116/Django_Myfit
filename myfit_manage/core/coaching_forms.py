
from django import forms

from .models import (
    CoachClientAssignment,
    CoachProfile,
    ClientProfile,
    WorkoutLog,
    ProgressEntry
)


# Form for administrators to assign a coach.
class AssignmentForm(forms.ModelForm):

    class Meta:
        model = CoachClientAssignment
        fields = ['client', 'coach']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Display only active users with the Coach role.
        self.fields['coach'].queryset = (
            CoachProfile.objects.filter(
                user__groups__name='Coach',
                user__is_active=True
            ).distinct()
        )

        # Display only active users with the Client role.
        self.fields['client'].queryset = (
            ClientProfile.objects.filter(
                user__groups__name='Client',
                user__is_active=True
            ).distinct()
        )


# Form for adding or editing a workout.
class WorkoutLogForm(forms.ModelForm):

    class Meta:
        model = WorkoutLog

        fields = [
            'workout_type',
            'workout_date',
            'duration_minutes',
            'notes'
        ]

        widgets = {
            'workout_date': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date'}
            ),
            'notes': forms.Textarea(
                attrs={'rows': 3}
            ),
        }


# Form for recording fitness measurements.
class ProgressEntryForm(forms.ModelForm):

    class Meta:
        model = ProgressEntry

        fields = [
            'measurement_type',
            'value',
            'unit',
            'recorded_on',
            'notes'
        ]

        widgets = {
            'recorded_on': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date'}
            ),
        }
