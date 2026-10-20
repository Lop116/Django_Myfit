
from django.db import models
from django.contrib.auth.models import User


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


# Create your models here.
