# ADDED: The public templates already expected these fields, but the models lacked them.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0012_supportticketmessage')]

    operations = [
        migrations.AlterField(
            model_name='websiteimage', name='is_active',
            field=models.BooleanField(default=True, help_text='Uncheck to hide this image on the public website.'),
        ),
        migrations.AddField(
            model_name='branch',
            name='operational_status',
            field=models.CharField(max_length=20, choices=[
                ('Open', 'Open'), ('Maintenance', 'Maintenance'),
                ('Coming soon', 'Coming soon'), ('Closed', 'Closed'),
            ], default='Open'),
        ),
        migrations.AddField(
            model_name='classsession',
            name='category',
            field=models.CharField(max_length=30, choices=[
                ('Strength', 'Strength'), ('HIIT', 'HIIT'), ('Yoga', 'Yoga'),
                ('Zumba', 'Zumba'), ('Mobility', 'Mobility'),
                ('Conditioning', 'Conditioning'),
            ], default='Strength'),
        ),
        migrations.AddField(
            model_name='classsession',
            name='description',
            field=models.TextField(blank=True),
        ),
    ]
