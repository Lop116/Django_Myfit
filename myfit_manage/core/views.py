from io import BytesIO

import qrcode
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as auth_login
from django.core import signing
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from .forms import RegistrationForm
from .membership_tokens import (
    create_membership_verification_token,
    get_membership_from_verification_token,
)
from .models import MembershipPass


# Create your views here.
def home(request):
    return render(request, 'myfit/home.html')

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('myfit:home')
    else:
        form = RegistrationForm()
    return render(request, 'myfit/register.html', {'form': form})

def branches(request):
    return render(request, 'myfit/branches.html')
def coaches(request):
    return render(request, 'myfit/coaches.html')
def classes(request):
    return render(request, 'myfit/classes.html')
def plans(request):
    return render(request, 'myfit/plans.html')


@login_required(login_url='myfit:login')
def membership_pass(request):
    try:
        member_pass = request.user.membership_pass
    except MembershipPass.DoesNotExist:
        member_pass = None

    qr_image_url = None
    if member_pass is not None:
        token = create_membership_verification_token(member_pass)
        qr_image_url = '{}?{}'.format(
            reverse('myfit:membership_qr'),
            urlencode({'token': token}),
        )

    return render(
        request,
        'myfit/membership_pass.html',
        {'member_pass': member_pass, 'qr_image_url': qr_image_url},
    )


@login_required(login_url='myfit:login')
def membership_qr(request):
    token = request.GET.get('token', '')
    try:
        member_pass = get_membership_from_verification_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest('This membership QR code is invalid or expired.')

    if member_pass is None or member_pass.user_id != request.user.pk:
        raise Http404

    verification_url = request.build_absolute_uri(
        '{}?{}'.format(
            reverse('myfit:membership_verify'),
            urlencode({'token': token}),
        )
    )
    image = qrcode.make(verification_url)
    image_buffer = BytesIO()
    image.save(image_buffer, format='PNG')
    return HttpResponse(image_buffer.getvalue(), content_type='image/png')


def membership_verify(request):
    token = request.GET.get('token', '')
    try:
        member_pass = get_membership_from_verification_token(token)
    except signing.BadSignature:
        return render(
            request,
            'myfit/membership_verify.html',
            {'verification_status': 'invalid'},
            status=400,
        )

    if member_pass is None:
        verification_status = 'invalid'
    else:
        verification_status = member_pass.current_status

    return render(
        request,
        'myfit/membership_verify.html',
        {'verification_status': verification_status},
    )


def contact(request):
    return render(request, 'myfit/contact.html')
