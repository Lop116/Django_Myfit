import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, FileExtensionValidator #< ---Loick 10/27
from django.db import models
from django.utils import timezone


# Image upload checks. These must be defined ABOVE the models that use them
# (Branch, CoachProfile, ClassSession, WebsiteImage), otherwise Django cannot import models.py.
def validate_myfit_image_size(file):
    if file.size > 5 * 1024 * 1024:
        raise ValidationError('Images must be 5 MB or smaller.')


MYFIT_IMAGE_VALIDATORS = [
    FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp']),
    validate_myfit_image_size,
]


class WorkoutRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exercise = models.CharField(max_length=120)
    workout_date = models.DateField()
    sets = models.PositiveIntegerField()
    reps = models.PositiveIntegerField()
    weight_kg = models.DecimalField(max_digits=7, decimal_places=1, default=0)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.exercise} - {self.user.username}"

    class Meta:
        ordering = ['-workout_date']


class ClientBooking(models.Model):
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='class_bookings',
    )

    class_name = models.CharField(max_length=120)
    class_date = models.DateField()
    start_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    trainer = models.CharField(max_length=120)
    location = models.CharField(max_length=120)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='confirmed',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.class_name}"

    class Meta:
        ordering = ['-class_date', '-start_time']


class MembershipPass(models.Model):
    class Plan(models.TextChoices):
        # Developer: Deshrao Saccaram
        NEUTRAL = 'membership', 'MyFit Membership'
        ACCESS = 'access', 'My Access'
        ACCESS_XL = 'xl', 'My Access XL'
        PREMIUM = 'premium', 'My Access Premium'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='membership_pass',
    )
    membership_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    plan = models.CharField(max_length=20, choices=Plan.choices)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    expiry_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.get_plan_display()} pass for {self.user}'

    @property
    def current_status(self):
        if (
            self.status == self.Status.ACTIVE
            and self.expiry_date is not None
            and self.expiry_date < timezone.localdate()
        ):
            return self.Status.EXPIRED
        return self.status

    @property
    def current_status_label(self):
        return self.Status(self.current_status).label


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.URLField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.title} for {self.user}'


# ==========================================================
# START TASK 2 - MEMBERSHIPS AND ATTENDANCE
# Developer: Deshrao Saccaram



class MembershipPlan(models.Model):
    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField()
    benefits = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ClientMembership(models.Model):

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('scheduled', 'Scheduled'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='client_memberships'
    )

    plan = models.ForeignKey(
        MembershipPlan,
        on_delete=models.PROTECT,
        related_name='client_memberships'
    )

    start_date = models.DateField()
    end_date = models.DateField()

    agreed_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.plan.name}"

    @property
    def current_status(self):
        if self.status in ('active', 'scheduled'):
            today = timezone.localdate()
            if self.end_date < today:
                return 'expired'
            if self.start_date > today:
                return 'scheduled'
            return 'active'
        return self.status


# Developer: Deshrao Saccaram
class MembershipChangeRequest(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    membership = models.ForeignKey(
        ClientMembership,
        on_delete=models.CASCADE,
        related_name='change_requests'
    )

    requested_plan = models.ForeignKey(
        MembershipPlan,
        on_delete=models.PROTECT,
        related_name='change_requests'
    )

    reason = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    requested_at = models.DateTimeField(auto_now_add=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_membership_requests'
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['membership'],
                condition=models.Q(status='pending'),
                name='unique_pending_change_request_per_membership',
            ),
        ]

    def __str__(self):
        return (
            f"{self.membership.user.username}: "
            f"{self.requested_plan.name} ({self.status})"
        )


class AttendanceVisit(models.Model):

    # TASK 2 - Gym attendance tracking

    membership = models.ForeignKey(
        ClientMembership,
        on_delete=models.PROTECT,
        related_name='attendance_visits'
    )

    check_in = models.DateTimeField(default=timezone.now)

    check_out = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return (
            f"{self.membership.user.username} - "
            f"{self.check_in}"
        )

    @property
    def is_checked_in(self):
        return self.check_out is None

    class Meta:
        ordering = ['-check_in']
        constraints = [
            models.UniqueConstraint(
                fields=['membership'],
                condition=models.Q(check_out__isnull=True),
                name='unique_open_visit_per_membership'
            )
        ]

# END TASK 2 - MEMBERSHIPS AND ATTENDANCE
# ==========================================================

#Loick--#################################################-----22/10/26 6.52>
class Branch(models.Model): #allows Django to map this class to a database table.
    name = models.CharField(max_length=120, unique=True) #short strings, maximum of 120 characters, unique name
    address = models.TextField() #Stores text without, field as required by default, field is non-null by default.
    phone = models.CharField(max_length=20, blank=True) #Stores the number as text because someone could put a + at the start
    email = models.EmailField(blank=True) #specialized CharField that validates email formatting
    opening_hours = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to='branches/', blank=True, validators=MYFIT_IMAGE_VALIDATORS)#<------ image
    created_at = models.DateTimeField(auto_now_add=True)#Stores when the branch record was created.
    updated_at = models.DateTimeField(auto_now=True)#Stores when the branch record was updated.

    class Meta:
        verbose_name_plural = "Branches"
        ordering = ["name"] #This tells Django to sort query results by name in ascending alphabetical order by default.

    def __str__(self):
        return self.name #This defines the human-readable text representation of a Branch object.

from .validators import validate_not_future #import the contrait

class CoachSpecialty(models.Model):
    name = models.CharField(max_length=60, unique=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        verbose_name_plural = "Coach specialties" #what name to display when referring to multiple records of the model
        ordering = ["name"]

    def __str__(self):
            return self.name

class ClientProfile(models.Model):
    user = models.OneToOneField( #Creates a one-to-one relationship between ClientProfile and User.
        settings.AUTH_USER_MODEL, #It tells Django which User model your application uses for authentication (login, passwords, usernames, etc.).
        on_delete=models.CASCADE, #Defines what happens when the referenced User is deleted.
        related_name="client_profile",) #Django to define a name for accessing a related model in the reverse direction.

    date_of_birth = models.DateField(null=True, blank=True,
                                     validators=[validate_not_future]) #chech if date is valide
    gender = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Client: {self.user.username}"

class CoachProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name="coach_profile",)

    branch = models.ForeignKey(Branch,on_delete=models.PROTECT, #prevent cascading delete from deleting all coach related to it
                               null=True,blank=True, #The database can store NULL for branch_id, A Django form can leave the branch field empty. We create a new coach account, but haven't assigned a gym branch yet.
                               related_name="coaches",)

    specialties = models.ManyToManyField(CoachSpecialty, #Creates a many-to-many relationship. It automatically creates a third table called a junction table.
                                blank=True, #a coach can be created without selecting any specialties yet.
                                related_name="coaches",)

    date_of_birth = models.DateField(null=True, blank=True,
                                    validators=[validate_not_future])

    gender = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)
    image = models.ImageField(upload_to='coaches/', blank=True, validators=MYFIT_IMAGE_VALIDATORS)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return f"Coach: {self.user.username}"
#<----
#jush===============
class ClassSession(models.Model):
    STATUS_CHOICES = [('Scheduled', 'Scheduled'), ('Cancelled', 'Cancelled'), ('Completed', 'Completed')]
    title = models.CharField(max_length=100)
    branch = models.ForeignKey('Branch', on_delete=models.CASCADE, related_name='classes')
    coach = models.ForeignKey('CoachProfile', on_delete=models.CASCADE, related_name='classes')
    date = models.DateField()
    time = models.TimeField()
    image = models.ImageField(upload_to='classes/', blank=True, validators=MYFIT_IMAGE_VALIDATORS)#<----Loick
    capacity = models.PositiveIntegerField(default=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Scheduled')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def spaces_left(self):
        return self.capacity - self.bookings.filter(status='Confirmed').count()

class ClassBooking(models.Model):
    STATUS_CHOICES = [('Confirmed', 'Confirmed'), ('Cancelled', 'Cancelled')]
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name='bookings')
    client = models.ForeignKey('ClientProfile', on_delete=models.CASCADE, related_name='bookings')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Confirmed')
    booked_at = models.DateTimeField(auto_now_add=True)
    #<----

#Ankush=================================
# Connects a client to their assigned coach.
class CoachClientAssignment(models.Model):

    coach = models.ForeignKey(
        'CoachProfile',
        on_delete=models.CASCADE,
        related_name='client_assignments'
    )

    # One client can have one assigned coach at a time.
    client = models.OneToOneField(
        'ClientProfile',
        on_delete=models.CASCADE,
        related_name='coaching_assignment'
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        # Ensure users have the appropriate roles.
        from .permissions import has_role

        if self.coach_id and not has_role(
            self.coach.user, 'Coach'
        ):
            raise ValidationError({
                'coach': 'The selected user must be a coach.'
            })

        if self.client_id and not has_role(
            self.client.user, 'Client'
        ):
            raise ValidationError({
                'client': 'The selected user must be a client.'
            })

    def __str__(self):
        return f"{self.client.user.username} - {self.coach.user.username}"


# Stores each workout completed by a client.
class WorkoutLog(models.Model):

    WORKOUT_TYPES = [
        ('strength', 'Strength Training'),
        ('cardio', 'Cardio'),
        ('flexibility', 'Flexibility'),
        ('sports', 'Sports'),
        ('other', 'Other'),
    ]

    client = models.ForeignKey(
        'ClientProfile',
        on_delete=models.CASCADE,
        related_name='workout_logs'
    )

    workout_type = models.CharField(
        max_length=20,
        choices=WORKOUT_TYPES
    )

    workout_date = models.DateField()

    # Duration is measured in minutes.
    duration_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )

    notes = models.TextField(blank=True, max_length=1000)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-workout_date', '-id']

    def clean(self):
        # Do not allow future workout dates.
        if self.workout_date and self.workout_date > timezone.localdate():
            raise ValidationError({
                'workout_date': 'Date cannot be in the future.'
            })

    def __str__(self):
        return f"{self.client.user.username} - {self.workout_type}"


# Stores a client's fitness measurements.
class ProgressEntry(models.Model):

    MEASUREMENT_TYPES = [
        ('weight', 'Weight'),
        ('distance', 'Distance'),
        ('repetitions', 'Repetitions'),
        ('duration', 'Duration'),
    ]

    UNIT_CHOICES = [
        ('kg', 'Kilograms'),
        ('lb', 'Pounds'),
        ('km', 'Kilometres'),
        ('m', 'Metres'),
        ('reps', 'Repetitions'),
        ('min', 'Minutes'),
        ('sec', 'Seconds'),
    ]

    # Each measurement type has valid units.
    ALLOWED_UNITS = {
        'weight': ('kg', 'lb'),
        'distance': ('km', 'm'),
        'repetitions': ('reps',),
        'duration': ('min', 'sec'),
    }

    client = models.ForeignKey(
        'ClientProfile',
        on_delete=models.CASCADE,
        related_name='progress_entries'
    )

    measurement_type = models.CharField(
        max_length=20,
        choices=MEASUREMENT_TYPES
    )

    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )

    unit = models.CharField(
        max_length=5,
        choices=UNIT_CHOICES
    )

    recorded_on = models.DateField()

    notes = models.CharField(
        max_length=255,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_on', '-id']

    def clean(self):
        errors = {}

        # Check that the selected unit is appropriate.
        allowed = self.ALLOWED_UNITS.get(
            self.measurement_type, ()
        )

        if self.unit not in allowed:
            errors['unit'] = 'Invalid measurement unit.'

        # Measurements must be positive.
        if self.value is not None and self.value <= 0:
            errors['value'] = 'Value must be positive.'

        # Repetitions must be whole numbers.
        if (
            self.measurement_type == 'repetitions'
            and self.value is not None
            and self.value % 1 != 0
        ):
            errors['value'] = 'Repetitions must be a whole number.'

        # Prevent future dates.
        if (
            self.recorded_on
            and self.recorded_on > timezone.localdate()
        ):
            errors['recorded_on'] = 'Date cannot be in the future.'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.client.user.username}: "
            f"{self.value} {self.unit}"
        )





    # MEDIA (simplest Django approach):---------------------------------------------------------
# - static/images/ contains artwork shipped with the project;
# - media/ contains pictures uploaded by administrators while the site runs.
# ImageField saves the picture's filename/path in the database, not its bytes.
# File-type and size checks below are small optional safeguards.
class WebsiteImage(models.Model):
    """One Admin-controlled image per public page/section."""
    # These choices prevent accidental extra records for the same placement.
    class Placement(models.TextChoices):
        HOME_HERO = 'home_hero', 'Homepage — hero background'
        HOME_ABOUT = 'home_about', 'Homepage — about section'
        HOME_COACHING = 'home_coaching', 'Homepage — coaching section'
        BRANCHES_HERO = 'branches_hero', 'Branches — header'
        COACHES_HERO = 'coaches_hero', 'Coaches — header'
        CLASSES_HERO = 'classes_hero', 'Classes — header'
        PLANS_HERO = 'plans_hero', 'Membership plans — header'
 
    # unique=True means one replacement image for each named website location.
    placement = models.CharField(max_length=30, choices=Placement.choices, unique=True)
    # upload_to creates the subdirectory underneath MEDIA_ROOT when uploading.
    image = models.ImageField(upload_to='website/', validators=MYFIT_IMAGE_VALIDATORS)
    alt_text = models.CharField(max_length=180, blank=True, help_text='Describe the picture for accessibility.')
    is_active = models.BooleanField(default=True, help_text='Uncheck to restore the original static picture.')
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = 'Website image'
        verbose_name_plural = 'Website images'
        ordering = ('placement',)
 
    def __str__(self):
        return self.get_placement_display()#----------------------------------------------------


#<-------------------------Loick
class SupportTicket(models.Model):
    """Stored contact enquiry or logged-in support ticket (never browser-only)."""
    KIND_CHOICES = [('enquiry', 'General enquiry'), ('ticket', 'Support ticket')]
    STATUS_CHOICES = [('open', 'Open'), ('progress', 'In progress'), ('resolved', 'Resolved')]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='support_tickets')
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default='enquiry')
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=160)
    topic = models.CharField(max_length=100)
    branch = models.CharField(max_length=120, blank=True)
    subject = models.CharField(max_length=130)
    message = models.TextField(max_length=2000)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        ordering = ['-created_at']
 
    def __str__(self):
        return f'MF-{self.pk}: {self.subject}'
#<----------------------------------------
