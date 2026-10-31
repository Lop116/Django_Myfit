"""Team handoff migration: editable class permissions, end time, booking integrity."""

from django.db import migrations, models
from django.db.models import Q


def enable_classes_for_seeded_plans(apps, schema_editor):
    Plan = apps.get_model('core', 'MembershipPlan')
    Plan.objects.filter(
        name__in=['My Access XL', 'My Access Premium']
    ).update(allows_classes=True)


class Migration(migrations.Migration):
    dependencies = [('core', '0014_seed_myfit_starter_data')]

    operations = [
        migrations.AddField(
            model_name='membershipplan',
            name='allows_classes',
            field=models.BooleanField(
                default=False,
                help_text='Allow this plan to book group classes.'
            ),
        ),
        migrations.AddField(
            model_name='classsession',
            name='end_time',
            field=models.TimeField(
                blank=True,
                null=True,
                help_text='Expected class end time; must be after the start time.'
            ),
        ),
        migrations.RunPython(
            enable_classes_for_seeded_plans,
            migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name='classbooking',
            constraint=models.UniqueConstraint(
                fields=['session', 'client'],
                condition=Q(status='Confirmed'),
                name='myfit_unique_confirmed_session_client',
            ),
        ),
    ]
