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