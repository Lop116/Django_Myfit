from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


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


#Loick>---------------------------------------------
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
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