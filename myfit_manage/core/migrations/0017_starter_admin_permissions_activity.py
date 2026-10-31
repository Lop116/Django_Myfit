"""Give the Admin role the model permissions used by MyFit admin pages."""

from django.db import migrations


def grant_admin_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model('auth', 'Group')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    group, _ = Group.objects.using(db_alias).get_or_create(name='Admin')
    permission_links = Group.permissions.through

    for model in apps.get_app_config('core').get_models():
        options = model._meta
        content_type, _ = ContentType.objects.using(db_alias).get_or_create(
            app_label=options.app_label,
            model=options.model_name,
        )
        permission_names = [
            (f'{action}_{options.model_name}', f'Can {action} {options.verbose_name}')
            for action in options.default_permissions
        ]
        permission_names.extend(options.permissions)
        for codename, name in permission_names:
            permission, _ = Permission.objects.using(db_alias).get_or_create(
                content_type_id=content_type.pk,
                codename=codename,
                defaults={'name': str(name)},
            )
            permission_links.objects.using(db_alias).get_or_create(
                group_id=group.pk,
                permission_id=permission.pk,
            )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_payment'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(grant_admin_permissions, migrations.RunPython.noop),
    ]
