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

# Form for editing client profile information.
# ModelForm automatically creates form fields based on ClientProfile.
class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = ClientProfile

        # Fields that the client can edit.
        fields = ("date_of_birth", "gender", "phone")

        # Display date_of_birth using an HTML date picker.
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"type": "date"}
            )
        }


# Form for editing coach profile information.
# ModelForm automatically creates form fields based on CoachProfile.
class CoachProfileForm(forms.ModelForm):
    class Meta:
        model = CoachProfile

        # Fields that the coach can edit.
        fields = ("date_of_birth", "gender", "phone", "bio")

        # Display date_of_birth using an HTML date picker.
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"type": "date"}
            )
        }

# Public directory, account management, and support forms.
from django.contrib.auth.password_validation import validate_password
from .models import Branch, CoachProfile, CoachSpecialty, SupportTicket
 
class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ['name', 'address', 'phone', 'email', 'opening_hours', 'image', 'is_active']
        widgets = {'address': forms.Textarea(attrs={'rows': 2}), 'opening_hours': forms.Textarea(attrs={'rows': 2})}
 
 
# These THREE User fields + the ONE phone field above = four details total.
class AccountDetailsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
 
 
class CoachAccountForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text='Required for new coaches; leave blank when editing to keep current password.')
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), required=False)
    specialties = forms.ModelMultipleChoiceField(queryset=CoachSpecialty.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    bio = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    image = forms.ImageField(required=False, help_text='Optional coach portrait, JPG/PNG/WEBP, maximum 5 MB.')
    remove_image = forms.BooleanField(required=False, label='Remove existing portrait')
    phone = forms.CharField(max_length=20, required=False)
    is_active = forms.BooleanField(required=False, initial=True, label='Account active')
 
    def __init__(self, *args, coach=None, **kwargs):
        self.coach = coach
        if coach and not args and 'initial' not in kwargs:
            kwargs['initial'] = {
                'username': coach.user.username, 'first_name': coach.user.first_name,
                'last_name': coach.user.last_name, 'email': coach.user.email,
                'branch': coach.branch_id, 'specialties': coach.specialties.all(),
                'bio': coach.bio, 'phone': coach.phone, 'is_active': coach.user.is_active,
            }
        super().__init__(*args, **kwargs)
        if coach and coach.image:
            self.fields['image'].help_text += f' Current: {coach.image.name}'
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        if coach and coach.branch_id:
            self.fields['branch'].queryset = Branch.objects.filter(pk=coach.branch_id) | Branch.objects.filter(is_active=True)
        self.fields['specialties'].queryset = CoachSpecialty.objects.filter(is_active=True)
        if coach:
            self.fields['specialties'].queryset = CoachSpecialty.objects.filter(pk__in=coach.specialties.values_list('pk', flat=True)) | CoachSpecialty.objects.filter(is_active=True)
 
    def clean_image(self):
        from .models import validate_myfit_image_size
        from django.core.validators import FileExtensionValidator
        image = self.cleaned_data['image']
        if image:
            FileExtensionValidator(allowed_extensions=['jpg','jpeg','png','webp'])(image)
            validate_myfit_image_size(image)
        return image
 
    def clean_username(self):
        value = self.cleaned_data['username'].strip()
        existing = User.objects.filter(username__iexact=value)
        if self.coach: existing = existing.exclude(pk=self.coach.user_id)
        if existing.exists(): raise forms.ValidationError('Username is already in use.')
        return value
 
    def clean_email(self):
        value = self.cleaned_data['email'].strip()
        existing = User.objects.filter(email__iexact=value)
        if self.coach: existing = existing.exclude(pk=self.coach.user_id)
        if existing.exists(): raise forms.ValidationError('Email address is already in use.')
        return value
 
    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.coach and not password:
            raise forms.ValidationError('Set an initial password for the new coach.')
        if password: validate_password(password, user=self.coach.user if self.coach else None)
        return password
 
 
class ContactSubmissionForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ['kind', 'name', 'email', 'topic', 'branch', 'subject', 'message']
        widgets = {'message': forms.Textarea(attrs={'rows': 5})}
 
    def clean_message(self):
        value = self.cleaned_data['message'].strip()
        if len(value) < 10:
            raise forms.ValidationError('Please enter at least 10 characters.')
        return value

#>.-----------------------------------------------
