import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


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


#Loick--#################################################-----22/10/26 6.52>
class Branch(models.Model): #allows Django to map this class to a database table.
    name = models.CharField(max_length=120, unique=True) #short strings, maximum of 120 characters, unique name
    address = models.TextField() #Stores text without, field as required by default, field is non-null by default.
    phone = models.CharField(max_length=20, blank=True) #Stores the number as text because someone could put a + at the start
    email = models.EmailField(blank=True) #specialized CharField that validates email formatting
    opening_hours = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
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
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator


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
