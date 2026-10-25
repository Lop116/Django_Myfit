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
        if (
            self.status == 'active'
            and self.end_date < timezone.localdate()
        ):
            return 'expired'
        return self.status


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