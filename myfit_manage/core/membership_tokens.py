import uuid

from django.core import signing

from .models import MembershipPass


MEMBERSHIP_QR_SALT = 'core.membership-pass.verification'
MEMBERSHIP_QR_MAX_AGE = 300


def create_membership_verification_token(membership_pass):
    return signing.dumps(
        {
            'membership_id': str(membership_pass.membership_id),
            'purpose': 'membership-verification',
        },
        salt=MEMBERSHIP_QR_SALT,
        compress=True,
    )


def get_membership_from_verification_token(token):
    payload = signing.loads(
        token,
        salt=MEMBERSHIP_QR_SALT,
        max_age=MEMBERSHIP_QR_MAX_AGE,
    )
    if not isinstance(payload, dict) or payload.get('purpose') != 'membership-verification':
        raise signing.BadSignature('Invalid membership verification token.')

    try:
        membership_id = uuid.UUID(payload['membership_id'])
    except (KeyError, TypeError, ValueError) as error:
        raise signing.BadSignature('Invalid membership verification token.') from error

    try:
        return MembershipPass.objects.select_related('user').get(membership_id=membership_id)
    except MembershipPass.DoesNotExist:
        return None
