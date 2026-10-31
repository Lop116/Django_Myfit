"""Manual payment administration (Task 6 + Frontend Person 6).
This does NOT process online payments or activate memberships.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.shortcuts import redirect, render
from .models import PaymentRecord, MembershipPlan
from .permissions import role_required


class PaymentRecordForm(forms.ModelForm):
    class Meta:
        model = PaymentRecord
        fields = ['user', 'plan', 'reference', 'amount', 'status', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = (get_user_model().objects
                                      .filter(groups__name='Client').distinct().order_by('username'))
        self.fields['plan'].queryset = MembershipPlan.objects.order_by('name')


@role_required('Admin')
def manage_payments(request):
    form = PaymentRecordForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Manual payment record saved. No online payment was charged.')
            return redirect('myfit:manage_payments')
        messages.error(request, 'Please correct the payment form.')
    payments = PaymentRecord.objects.select_related('user', 'plan').all()
    return render(request, 'myfit/manage_payments.html', {
        'form': form, 'payments': payments,
        'paid_count': payments.filter(status='paid').count(),
        'paid_total': payments.filter(status='paid').aggregate(amount=Sum('amount'))['amount'] or 0,
    })