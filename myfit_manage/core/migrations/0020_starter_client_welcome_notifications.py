"""Add an initial notification to starter client accounts."""

from django.db import migrations


def create_welcome_notifications(apps, schema_editor):
    database = schema_editor.connection.alias
    Notification = apps.get_model('core', 'Notification')
    User = apps.get_model('auth', 'User')

    for username in ('demo_client1', 'demo_client2'):
        try:
            user = User.objects.using(database).get(username=username)
        except User.DoesNotExist:
            continue
        Notification.objects.using(database).get_or_create(
            user_id=user.pk,
            title='Welcome to MyFit',
            defaults={
                'message': 'Your MyFit membership and training dashboard are ready.',
                'link': '/client-dashboard/',
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0019_starter_admin_and_coaching_assignments'),
    ]

    operations = [
        migrations.RunPython(
            create_welcome_notifications,
            migrations.RunPython.noop,
        ),
    ]
