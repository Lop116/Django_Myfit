#Loick<------
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
 
class Migration(migrations.Migration):
    dependencies = [('core', '0009_coachclientassignment_progressentry_workoutlog'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name='SupportTicket', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('kind', models.CharField(max_length=12, choices=[('enquiry','General enquiry'),('ticket','Support ticket')], default='enquiry')),
        ('name', models.CharField(max_length=100)),
        ('email', models.EmailField(max_length=160)),
        ('topic', models.CharField(max_length=100)),
        ('branch', models.CharField(max_length=120, blank=True)),
        ('subject', models.CharField(max_length=130)),
        ('message', models.TextField(max_length=2000)),
        ('status', models.CharField(max_length=12, choices=[('open','Open'),('progress','In progress'),('resolved','Resolved')], default='open')),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='support_tickets', to=settings.AUTH_USER_MODEL)),
    ], options={'ordering':['-created_at']})]
