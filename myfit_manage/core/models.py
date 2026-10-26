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
