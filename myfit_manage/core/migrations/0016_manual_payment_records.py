"""Manual payment ledger. Does not capture card payments or auto-activate memberships."""
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0012_supportticketmessage'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='PaymentRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(max_length=80, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(Decimal('0.01'))])),
                ('status', models.CharField(max_length=10, choices=[('pending','Pending'),('paid','Paid'),('failed','Failed'),('refunded','Refunded')], default='pending')),
                ('notes', models.TextField(blank=True)),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payment_records', to='core.membershipplan')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='myfit_payments', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-recorded_at']},
        ),
    ]