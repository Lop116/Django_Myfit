from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import MembershipPlan


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'autocomplete': 'given-name',
            'placeholder': 'First name',
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'autocomplete': 'family-name',
            'placeholder': 'Last name',
        }),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'autocomplete': 'email',
            'placeholder': 'you@example.com',
        }),
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('first_name', 'last_name', 'email', 'username')
        widgets = {
            'username': forms.TextInput(attrs={
                'autocomplete': 'username',
                'placeholder': 'Choose a username',
            }),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        users = get_user_model().objects.filter(email__iexact=email)
        if self.instance.pk:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise forms.ValidationError('An account with this email address already exists.')
        return email


class MembershipVerificationForm(forms.Form):
    verification_input = forms.CharField(
        label='Membership QR link or token',
        max_length=4096,
        widget=forms.TextInput(attrs={
            'autocomplete': 'off',
            'placeholder': 'Paste the membership verification link or token',
        }),
    )


# ==========================================================
# START TASK 2 - MEMBERSHIPS AND ATTENDANCE
# Developer: Deshrao Saccaram


class MembershipPlanForm(forms.ModelForm):

    class Meta:
        model = MembershipPlan

        fields = [
            'name',
            'price',
            'duration_days',
            'benefits',
            'is_active',
        ]

        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Enter membership plan name',
            }),
            'price': forms.NumberInput(attrs={
                'min': '0',
                'step': '0.01',
            }),
            'duration_days': forms.NumberInput(attrs={
                'min': '1',
            }),
            'benefits': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Describe membership benefits',
            }),
        }

    def clean_price(self):
        price = self.cleaned_data['price']

        if price <= 0:
            raise forms.ValidationError(
                'Membership price must be greater than zero.'
            )

        return price

    def clean_duration_days(self):
        duration = self.cleaned_data['duration_days']

        if duration <= 0:
            raise forms.ValidationError(
                'Membership duration must be greater than zero.'
            )

        return duration


# END TASK 2 - MEMBERSHIPS AND ATTENDANCE
# ==========================================================