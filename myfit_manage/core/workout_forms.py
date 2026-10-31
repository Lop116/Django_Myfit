from django import forms
from django.utils import timezone
from .models import WorkoutRecord
 
 
class WorkoutRecordForm(forms.ModelForm):
    class Meta:
        model = WorkoutRecord
        fields = ['exercise', 'workout_date', 'sets', 'reps', 'weight_kg', 'notes']
 
    def clean_workout_date(self):
        value = self.cleaned_data['workout_date']
        if value > timezone.localdate():
            raise forms.ValidationError('Workout date cannot be in the future.')
        return value
 
    def clean_sets(self):
        value = self.cleaned_data['sets']
        if value < 1 or value > 100:
            raise forms.ValidationError('Sets must be between 1 and 100.')
        return value
 
    def clean_reps(self):
        value = self.cleaned_data['reps']
        if value < 1 or value > 1000:
            raise forms.ValidationError('Reps must be between 1 and 1000.')
        return value
 
    def clean_weight_kg(self):
        value = self.cleaned_data['weight_kg']
        if value < 0 or value > 10000:
            raise forms.ValidationError('Weight must be between 0 and 10000 kg.')
        return value
