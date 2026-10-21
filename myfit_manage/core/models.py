import uuid

from django.db import models
from django.conf import settings
from django.utils import timezone


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
