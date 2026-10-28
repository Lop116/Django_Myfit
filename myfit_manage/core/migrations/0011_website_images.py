#Loick
from django.db import migrations, models
import core.models
import django.core.validators
 
 
class Migration(migrations.Migration):
    dependencies = [('core', '0010_supportticket')]
    operations = [
        migrations.CreateModel(name='WebsiteImage', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('placement', models.CharField(max_length=30, choices=[
                ('home_hero','Homepage — hero background'), ('home_about','Homepage — about section'),
                ('home_coaching','Homepage — coaching section'), ('branches_hero','Branches — header'),
                ('coaches_hero','Coaches — header'), ('classes_hero','Classes — header'),
                ('plans_hero','Membership plans — header')], unique=True)),
            ('image', models.ImageField(upload_to='website/', validators=[
                django.core.validators.FileExtensionValidator(allowed_extensions=['jpg','jpeg','png','webp']),
                core.models.validate_myfit_image_size])),
            ('alt_text', models.CharField(max_length=180, blank=True, help_text='Describe the picture for accessibility.')),
            ('is_active', models.BooleanField(default=True, help_text='Uncheck to restore the original static picture.')),
            ('updated_at', models.DateTimeField(auto_now=True)),
        ], options={'verbose_name':'Website image','verbose_name_plural':'Website images','ordering':('placement',)}),
        migrations.AddField(model_name='branch', name='image', field=models.ImageField(upload_to='branches/', blank=True,
            validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['jpg','jpeg','png','webp']), core.models.validate_myfit_image_size])),
        migrations.AddField(model_name='coachprofile', name='image', field=models.ImageField(upload_to='coaches/', blank=True,
            validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['jpg','jpeg','png','webp']), core.models.validate_myfit_image_size])),
        migrations.AddField(model_name='classsession', name='image', field=models.ImageField(upload_to='classes/', blank=True,
            validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['jpg','jpeg','png','webp']), core.models.validate_myfit_image_size])),
    ]
