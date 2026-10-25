#Loick  Creating the group at the start
from django.db import migrations


def create_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    db_alias = schema_editor.connection.alias

    roles = ["Client", "Coach", "Admin"]

    for role in roles:
        Group.objects.using(db_alias).get_or_create(
            name=role
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_coachspecialty_clientprofile_coachprofile"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_roles,
            migrations.RunPython.noop
        ),
    ]