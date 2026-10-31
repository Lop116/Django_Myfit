"""One-time starter data, part 2 (runs once, through `python manage.py migrate`).

Completes the starter set created by 0014 without touching anything an
administrator may already have edited:

* gives the "Admin" role group every core permission, so Admin-role accounts
  can use the membership, attendance and plan tools (they previously required
  per-user permissions nobody granted);
* creates ONE administrator account (`myfit_admin`) with an UNUSABLE password.
  No plaintext password exists anywhere in the repository. Set it with
  `python manage.py changepassword myfit_admin` or
  `python manage.py myfit_set_passwords`;
* links the starter clients to starter coaches, records example attendance,
  workouts and progress, and creates the notifications that the real
  booking / class-assignment events would have produced.

Every step only fills gaps (get_or_create / exists checks) and skips anything
whose starter records were removed, so nothing is duplicated or resurrected.
Like every migration it never re-runs on server restarts.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.utils import timezone

ADMIN_USERNAME = 'myfit_admin'
ASSIGNMENTS = (('demo_client1', 'demo_maya'), ('demo_client2', 'demo_sarah'))


def _grant_admin_permissions(apps):
    # Permissions are normally created after all migrations (post_migrate);
    # create them now so they can be attached to the Admin group.
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    for app_config in global_apps.get_app_configs():
        if app_config.label in ('core', 'auth'):
            create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    admin_group, _ = Group.objects.get_or_create(name='Admin')
    admin_group.permissions.add(*Permission.objects.filter(content_type__app_label='core'))
    return admin_group


def populate(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    ClassSession = apps.get_model('core', 'ClassSession')
    ClassBooking = apps.get_model('core', 'ClassBooking')
    ClientProfile = apps.get_model('core', 'ClientProfile')
    CoachProfile = apps.get_model('core', 'CoachProfile')
    ClientMembership = apps.get_model('core', 'ClientMembership')
    AttendanceVisit = apps.get_model('core', 'AttendanceVisit')
    CoachClientAssignment = apps.get_model('core', 'CoachClientAssignment')
    WorkoutRecord = apps.get_model('core', 'WorkoutRecord')
    WorkoutLog = apps.get_model('core', 'WorkoutLog')
    ProgressEntry = apps.get_model('core', 'ProgressEntry')
    Notification = apps.get_model('core', 'Notification')

    admin_group = _grant_admin_permissions(apps)

    # 1 administrator, created only if that username is free.
    if not User.objects.filter(username=ADMIN_USERNAME).exists():
        admin = User.objects.create(
            username=ADMIN_USERNAME, first_name='MyFit', last_name='Administrator',
            email='admin@myfit.invalid', password=make_password(None),
            is_staff=True, is_superuser=True, is_active=True,
        )
        admin.groups.add(admin_group)

    # Starter classes from 0014 had no end time; give them a 60-minute slot.
    for session in ClassSession.objects.filter(
        end_time__isnull=True, coach__user__username__startswith='demo_',
    ):
        start = datetime.combine(session.date, session.time)
        session.end_time = (start + timedelta(minutes=60)).time()
        session.save(update_fields=['end_time'])

    today = timezone.localdate()
    now = timezone.now()
    for client_username, coach_username in ASSIGNMENTS:
        client = ClientProfile.objects.filter(user__username=client_username).first()
        coach = CoachProfile.objects.filter(user__username=coach_username).first()
        if client is None or coach is None:
            continue  # starter record removed by an administrator: skip.

        if not CoachClientAssignment.objects.filter(client=client).exists():
            CoachClientAssignment.objects.create(client=client, coach=coach)
            Notification.objects.create(
                user=coach.user, title='New client assigned',
                message=f'{client.user.first_name} {client.user.last_name} is now in your client list.',
                link='/coach/clients/',
            )

        # One completed gym visit on the client's current membership.
        membership = ClientMembership.objects.filter(
            user=client.user, status='active', start_date__lte=today, end_date__gte=today,
        ).first()
        if membership and not AttendanceVisit.objects.filter(membership=membership).exists():
            AttendanceVisit.objects.create(
                membership=membership,
                check_in=now - timedelta(hours=2),
                check_out=now - timedelta(hours=1),
            )

        if not WorkoutRecord.objects.filter(user=client.user).exists():
            for days_ago, exercise, sets, reps, weight in (
                (3, 'Barbell squat', 4, 8, '60.0'),
                (1, 'Bench press', 4, 10, '45.0'),
            ):
                WorkoutRecord.objects.create(
                    user=client.user, exercise=exercise,
                    workout_date=today - timedelta(days=days_ago),
                    sets=sets, reps=reps, weight_kg=Decimal(weight),
                )

        if not WorkoutLog.objects.filter(client=client).exists():
            WorkoutLog.objects.create(
                client=client, workout_type='strength',
                workout_date=today - timedelta(days=1), duration_minutes=55,
                notes='Starter example: full-body strength session.',
            )

        if not ProgressEntry.objects.filter(client=client).exists():
            for days_ago, value in ((14, '78.50'), (1, '77.20')):
                ProgressEntry.objects.create(
                    client=client, measurement_type='weight', unit='kg',
                    value=Decimal(value), recorded_on=today - timedelta(days=days_ago),
                )

    # Notifications that the real booking/assignment events would have sent.
    for booking in ClassBooking.objects.filter(
        status='Confirmed', client__user__username__startswith='demo_',
    ).select_related('session', 'client__user'):
        user = booking.client.user
        title = 'Class booking confirmed'
        if not Notification.objects.filter(user=user, title=title).exists():
            session = booking.session
            Notification.objects.create(
                user=user, title=title,
                message=f'You booked {session.title} on {session.date:%d %b %Y} at {session.time:%H:%M}.',
                link='/client-bookings/',
            )

    for session in ClassSession.objects.filter(
        coach__user__username__startswith='demo_',
    ).select_related('coach__user'):
        user = session.coach.user
        message = f'You are assigned to {session.title} on {session.date:%d %b %Y} at {session.time:%H:%M}.'
        if not Notification.objects.filter(user=user, message=message).exists():
            Notification.objects.create(
                user=user, title='Class assigned', message=message, link='/manage-classes/',
            )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_protect_history_draft_classes'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]
    # No reverse: unapplying must never delete data administrators edited.
    operations = [migrations.RunPython(populate, migrations.RunPython.noop)]
