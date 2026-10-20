
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

class WorkoutRecord(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    exercise = models.CharField(max_length=120)

    workout_date = models.DateField()

    sets = models.PositiveIntegerField()

    reps = models.PositiveIntegerField()

    weight_kg = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        default=0
    )

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
        related_name='class_bookings'
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
        default='confirmed'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.class_name}"

    class Meta:
        ordering = ['-class_date', '-start_time']