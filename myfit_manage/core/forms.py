from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from .models import (
    ClientMembership,
    MembershipChangeRequest,
    MembershipPlan,
)

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

# ==========================================================
# START TASK 2 - CLIENT MEMBERSHIP ASSIGNMENT FORM

class ClientMembershipAssignmentForm(forms.Form):

    user = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        label="Select Client"
    )

    plan = forms.ModelChoiceField(
        queryset=MembershipPlan.objects.none(),
        label="Membership Plan"
    )

    start_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Start Date"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["user"].queryset = (
            get_user_model().objects
            .filter(is_active=True, is_staff=False, is_superuser=False)
            .order_by("username")
        )

        self.fields["plan"].queryset = (
            MembershipPlan.objects
            .filter(is_active=True)
            .order_by("name")
        )

# END TASK 2 - CLIENT MEMBERSHIP ASSIGNMENT FORM

# ==========================================================
# MYFIT - TASK 2: MEMBERSHIP CHANGE REQUEST FORM
# Developer: Deshrao Saccaram


class MembershipChangeRequestForm(forms.ModelForm):

    class Meta:
        model = MembershipChangeRequest

        fields = [
            'requested_plan',
            'reason',
        ]

        labels = {
            'requested_plan': 'Select New Membership Plan',
            'reason': 'Reason for Change (Optional)',
        }

        widgets = {
            'reason': forms.Textarea(
                attrs={
                    'rows': 4,
                    'placeholder': 'Why would you like to change your plan?'
                }
            )
        }

    def __init__(self, *args, current_plan=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Show only active membership plans.
        plans = MembershipPlan.objects.filter(
            is_active=True
        )

        # Exclude the client's current plan.
        if current_plan is not None:
            plans = plans.exclude(pk=current_plan.pk)

        self.fields['requested_plan'].queryset = (
            plans.order_by('name')
        )

# END TASK 2 - MEMBERSHIP CHANGE REQUEST FORM


# ==========================================================
# TASK 2 - ATTENDANCE MANAGEMENT
# Developer: Deshrao Saccaram


# Developer: Deshrao Saccaram
class AttendanceMembershipChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, membership):
        return (
            f'{membership.user.get_full_name() or membership.user.username} '
            f'- {membership.plan.name} '
            f'({membership.start_date:%d %b %Y} - {membership.end_date:%d %b %Y})'
        )


class AttendanceCheckInForm(forms.Form):
    membership = AttendanceMembershipChoiceField(
        queryset=ClientMembership.objects.none(),
        label='Client Membership',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields['membership'].queryset = (
            ClientMembership.objects
            .filter(
                user__is_active=True,
                user__is_staff=False,
                user__is_superuser=False,
                status__in=('active', 'scheduled'),
                start_date__lte=today,
                end_date__gte=today,
            )
            .select_related('user', 'plan')
            .order_by('user__username', 'plan__name')
        )

    def clean_membership(self):
        membership = self.cleaned_data['membership']
        if membership.current_status != 'active':
            raise forms.ValidationError(
                'This membership is not currently valid for check-in.'
            )
        return membership

# END TASK 2 - ATTENDANCE MANAGEMENT

#Loick>---------------------------------------------
from .models import ClientProfile, CoachProfile

User = get_user_model()
class ClientRegistrationForm(UserCreationForm):#means that our class inherits from Django's built-in UserCreationForm.
    email = forms.EmailField(required=True)
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")
    def clean_email(self): # check for a better explanation for why clean<--------------------
        email = self.cleaned_data["email"].strip().lower() # check for a better explanation for why self.clean <--------------------
        if User.objects.filter(email__iexact=email).exists():   # check for a better explanation <--------------------
            raise forms.ValidationError("That email address is already in use.")
        return email

class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = ClientProfile
        fields = ("date_of_birth", "gender", "phone")
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

class CoachProfileForm(forms.ModelForm):
    class Meta:
        model = CoachProfile
        fields = ("date_of_birth", "gender", "phone", "bio")
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

#>.-----------------------------------------------
