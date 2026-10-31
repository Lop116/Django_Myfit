import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# Production must set DJANGO_SECRET_KEY; the fallback is for local development only.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-wgp4y*v@5oe2dz4z3(zpjxm1usj@u@o^@-dgde@x$bq5y61=y1',
)

# SECURITY WARNING: don't run with debug turned on in production!
# Local development keeps DEBUG on; set DJANGO_DEBUG=0 in production.
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if h]
