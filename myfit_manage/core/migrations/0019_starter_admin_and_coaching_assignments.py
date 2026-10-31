"""Ensure the demo administrator and coach-client links exist on fresh installs."""

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_starter_admin_and_assignments(apps, schema_editor):
    database = schema_editor.connection.alias
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    Group = apps.get_model('auth', 'Group')
    CoachProfile = apps.get_model('core', 'CoachProfile')
    ClientProfile = apps.get_model('core', 'ClientProfile')
    CoachClientAssignment = apps.get_model('core', 'CoachClientAssignment')

    admin, created = User.objects.using(database).get_or_create(
        username='myfit_admin',
        defaults={
            'email': 'admin@myfit.local',
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
            'password': make_password(None),
        },
    )
    if not created:
        admin.is_staff = True
        admin.is_superuser = True
        admin.save(update_fields=['is_staff', 'is_superuser'])
    admin_group, _ = Group.objects.using(database).get_or_create(name='Admin')
    User._meta.get_field('groups').remote_field.through.objects.using(database).get_or_create(
        user_id=admin.pk,
        group_id=admin_group.pk,
    )

    assignments = (
        ('demo_client1', 'demo_maya'),
        ('demo_client2', 'demo_daniel'),
    )
    for client_username, coach_username in assignments:
        try:
            client = ClientProfile.objects.using(database).get(
                user__username=client_username,
            )
            coach = CoachProfile.objects.using(database).get(
                user__username=coach_username,
            )
        except (ClientProfile.DoesNotExist, CoachProfile.DoesNotExist):
            continue
        CoachClientAssignment.objects.using(database).get_or_create(
            client_id=client.pk,
            defaults={'coach_id': coach.pk},
        )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0018_classbooking_cancelled_at_alter_classsession_status'),
    ]

    operations = [
        migrations.RunPython(
            create_starter_admin_and_assignments,
            migrations.RunPython.noop,
        ),
    ]
