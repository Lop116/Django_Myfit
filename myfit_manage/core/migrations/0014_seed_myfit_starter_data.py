"""One-time starter database data. Applied ONLY by `python manage.py migrate`.

ADDED: The data is saved in DB rows and all image files are copied to MEDIA_ROOT.
Admins can then edit, deactivate, delete, and replace photos. Deleted seed rows
are NOT re-created on each runserver restart (unlike AppConfig.ready signals).
"""
from datetime import timedelta, time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.contrib.auth.hashers import make_password
from django.db import migrations
from django.utils import timezone


BRANCHES = [
    ('Caudan Waterfront', 'Dias Pier Building, 1st floor, Caudan Waterfront, Port Louis', 'Open', 'Mon–Sun: contact reception for hours', 'branch-caudan.webp'),
    ('Trianon', 'Emerald Park, Trianon, Mauritius', 'Open', 'Mon–Sun: contact reception for hours', 'branch-trianon.webp'),
    ('Riche Terre', 'Riche Terre Mall, Riche Terre, Mauritius', 'Open', 'Mon–Sun: contact reception for hours', 'branch-riche-terre.webp'),
    ('Plaisance Mall', 'Plaisance Mall, Mauritius', 'Coming soon', 'Opening soon', 'branch-plaisance.webp'),
]

# Accounts have unusable passwords by default. Admin sets credentials securely.
COACHES = [
    ('demo_maya', 'Maya', 'Roberts', 'Caudan Waterfront', ('Strength', 'Conditioning'), 'coach-maya.webp', 'Strength and full-body coaching.'),
    ('demo_daniel', 'Daniel', 'Kim', 'Trianon', ('HIIT', 'Conditioning'), 'coach-daniel.webp', 'Cardio, HIIT and high-energy sessions.'),
    ('demo_sarah', 'Sarah', 'M', 'Riche Terre', ('Yoga', 'Mobility'), 'coach-sarah.webp', 'Flexibility, mobility and mindful training.'),
    ('demo_ryan', 'Ryan', 'B', 'Caudan Waterfront', ('Zumba', 'HIIT'), 'coach-ryan.webp', 'Dance fitness and dynamic group training.'),
]
CLIENTS = [
    ('demo_client1', 'Alex', 'Martin'),
    ('demo_client2', 'Jordan', 'Taylor'),
]
PLANS = [
    ('My Access', '1249.00', 'Unlimited gym access\nOne free trial for a friend or family member'),
    ('My Access XL', '1399.00', 'Unlimited gym access\nMYGYM360 MRU/REU/FR access\nMembership suspension\nUnlimited fitness classes\nOne guest pass'),
    ('My Access Premium', '1549.00', 'All My Access XL benefits\nOne personal training session\nPriority class booking\nExtended suspension\nTwo guest passes'),
]
CLASSES = [
    ('Strength Foundations', 'Strength', 'Learn effective lifting fundamentals.', 'Caudan Waterfront', 'demo_maya', 2, time(7, 30), 16, 'class-strength.webp'),
    ('Morning HIIT Circuit', 'HIIT', 'Intervals to build endurance.', 'Trianon', 'demo_daniel', 3, time(8, 0), 20, 'class-hiit.webp'),
    ('Yoga Flow', 'Yoga', 'Breathing and mobility through a flowing sequence.', 'Riche Terre', 'demo_sarah', 4, time(9, 0), 18, 'class-yoga.webp'),
    ('Zumba Dance Fit', 'Zumba', 'Music-powered dance cardio workout.', 'Caudan Waterfront', 'demo_ryan', 5, time(17, 30), 25, 'class-zumba.webp'),
    ('Full Body Conditioning', 'Conditioning', 'A challenging and adaptable full-body workout.', 'Trianon', 'demo_maya', 6, time(18, 0), 18, 'class-strength.webp'),
    ('Core & Mobility', 'Mobility', 'Train your core and improve movement quality.', 'Riche Terre', 'demo_sarah', 7, time(8, 30), 15, 'class-yoga.webp'),
]
SITES = [
    ('home_hero', 'homepage_images/hero-myfit.webp', 'MyFit homepage gym training'),
    ('home_about', 'homepage_images/coaching-myfit.webp', 'Training space'),
    ('home_coaching', 'homepage_images/training-myfit.webp', 'Coach training at MyFit'),
    ('branches_hero', 'branches/branches-hero.webp', 'MyFit branches'),
    ('coaches_hero', 'coaches/coaches-hero.webp', 'MyFit coaches'),
    ('classes_hero', 'classes/classes-hero.webp', 'MyFit group fitness'),
    ('plans_hero', 'homepage_images/hero-myfit.webp', 'MyFit gym training'),
]


def _store_image(record, field, folder, filename):
    """Copy bundled starter image to user-upload storage, not a static HTML URL."""
    image_path = Path(settings.BASE_DIR) / 'core' / 'static' / 'images' / folder / filename
    if not image_path.is_file():
        return  # Keep record even if a deployed image wasn't packaged.
     # Reuse an already-copied file instead of writing a new random-suffixed
    # copy on every fresh database (e.g. each test run) into MEDIA_ROOT.
    model_field = record._meta.get_field(field)
    stored_name = model_field.generate_filename(record, filename)
    if model_field.storage.exists(stored_name):
        setattr(record, model_field.attname, stored_name)
        record.save(update_fields=[model_field.attname])
        return
    with image_path.open('rb') as f:
        getattr(record, field).save(filename, File(f), save=True)


def populate_myfit(apps, schema_editor):
    # Historical models are required inside data migrations.
    Branch = apps.get_model('core', 'Branch')
    CoachSpecialty = apps.get_model('core', 'CoachSpecialty')
    CoachProfile = apps.get_model('core', 'CoachProfile')
    ClientProfile = apps.get_model('core', 'ClientProfile')
    ClassSession = apps.get_model('core', 'ClassSession')
    ClassBooking = apps.get_model('core', 'ClassBooking')
    MembershipPlan = apps.get_model('core', 'MembershipPlan')
    ClientMembership = apps.get_model('core', 'ClientMembership')
    WebsiteImage = apps.get_model('core', 'WebsiteImage')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Group = apps.get_model('auth', 'Group')
    coach_group, _ = Group.objects.get_or_create(name='Coach')
    client_group, _ = Group.objects.get_or_create(name='Client')
    branches = {}
    for name, address, status, hours, image in BRANCHES:
        obj, made = Branch.objects.get_or_create(name=name, defaults={
            'address': address, 'opening_hours': hours,
            'operational_status': status, 'is_active': True,
        })
        branches[name] = obj
        if made:
            _store_image(obj, 'image', 'branches', image)

    specialties = {}
    for name in ('Strength', 'Conditioning', 'HIIT', 'Yoga', 'Mobility', 'Zumba'):
        specialties[name], _ = CoachSpecialty.objects.get_or_create(name=name)

    coaches = {}
    for username, first, last, branch, spec_names, portrait, bio in COACHES:
        user, made = User.objects.get_or_create(username=username, defaults={
            'first_name': first, 'last_name': last,
            'email': f'{username}@example.invalid',
            'password': make_password(None), 'is_active': True,
        })
        user.groups.add(coach_group)
        profile, made_profile = CoachProfile.objects.get_or_create(user=user, defaults={
            'branch': branches[branch], 'bio': bio,
        })
        coaches[username] = profile
        if made_profile:
            profile.specialties.set([specialties[n] for n in spec_names])
            _store_image(profile, 'image', 'coaches', portrait)

    for username, first, last in CLIENTS:
        user, _ = User.objects.get_or_create(username=username, defaults={
            'first_name': first, 'last_name': last,
            'email': f'{username}@example.invalid',
            'password': make_password(None), 'is_active': True,
        })
        user.groups.add(client_group)
        ClientProfile.objects.get_or_create(user=user)

    plans = {}
    for name, price, benefits in PLANS:
        plan, _ = MembershipPlan.objects.get_or_create(name=name, defaults={
            'price': Decimal(price), 'duration_days': 30,
            'benefits': benefits, 'is_active': True,
        })
        plans[name] = plan

    # Sample memberships let the two demo clients try booking after passwords
    # are set; no booking is made automatically and admins can edit them.
    for index, (username, _, _) in enumerate(CLIENTS):
        user = User.objects.get(username=username)
        plan = plans['My Access XL' if index == 0 else 'My Access Premium']
        ClientMembership.objects.get_or_create(user=user, plan=plan, defaults={
            'start_date': timezone.localdate(),
            'end_date': timezone.localdate() + timedelta(days=30),
            'agreed_price': plan.price, 'status': 'active',
        })

    today = timezone.localdate()
    for title, category, description, branch, coach, days, at, capacity, image in CLASSES:
        # Seed exactly once; no repeated class generation on server restart.
        obj, made = ClassSession.objects.get_or_create(
            title=title, branch=branches[branch],
            coach=coaches[coach],
            defaults={'category': category, 'description': description,
                      'date': today + timedelta(days=days),
                      'time': at, 'capacity': capacity, 'status': 'Scheduled'},
        )
        if made:
            _store_image(obj, 'image', 'classes', image)

    # Two real bookings make the management statistics and attendance lists useful.
    # get_or_create prevents duplicate records if a migration is interrupted.
    for username, class_title in (
        ('demo_client1', 'Strength Foundations'),
        ('demo_client2', 'Yoga Flow'),
    ):
        client = ClientProfile.objects.get(user__username=username)
        session = ClassSession.objects.get(title=class_title)
        ClassBooking.objects.get_or_create(
            session=session, client=client, defaults={'status': 'Confirmed'},
        )

    for place, source, alt in SITES:
        obj, made = WebsiteImage.objects.get_or_create(placement=place, defaults={
            'alt_text': alt, 'is_active': True,
        })
        if made:
            _store_image(obj, 'image', *source.rsplit('/', 1))


class Migration(migrations.Migration):
    dependencies = [('core', '0013_branch_status_class_details')]
    # Empty reverse avoids deleting real content an admin may have edited later.
    operations = [migrations.RunPython(populate_myfit, migrations.RunPython.noop)]
