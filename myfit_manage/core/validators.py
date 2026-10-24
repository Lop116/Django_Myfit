#Loick

#Without our custom validator, Django's DateField checks that the value is a valid date, but doesn't automatically reject future dates.
from django.core.exceptions import ValidationError #ValidationError is used when data doesn't satisfy a validation rule.
from django.utils import timezone

def validate_not_future(value):
    

    if value and value > timezone.localdate(): # Reject birth dates after today's date
        """First value - Checks whether a value was provided.
        This matters because date of birth may be optional in our MyFit profiles."""
        
        raise ValidationError("Date of birth cannot be in the future.")
        """Second value - Compares the entered birth date against today's date in Django's active timezone."""