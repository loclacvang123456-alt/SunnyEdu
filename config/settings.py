import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'development-only-not-for-production')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
TESTING = 'test' in sys.argv
# Teacher OTP bypass (default enabled). Set TEACHER_OTP_BYPASS=0 in environment to restore teacher OTP verification.
TEACHER_OTP_BYPASS = os.environ.get('TEACHER_OTP_BYPASS', '1') == '1'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'django.contrib.postgres', 'django_otp', 'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static', 'two_factor',
    'apps.accounts', 'apps.classes', 'apps.content', 'apps.assignments',
    'apps.grading', 'apps.reporting', 'apps.core',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', 'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'apps.core.seasonal.context', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'eduweb'),
        'USER': os.environ.get('POSTGRES_USER', 'eduweb'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'eduweb-local'),
        'HOST': os.environ.get('POSTGRES_HOST', '127.0.0.1'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'DISABLE_SERVER_SIDE_CURSORS': os.environ.get('POSTGRES_PORT', '5432') == '6543',
    }
}
AUTH_USER_MODEL = 'accounts.User'
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
PRIVATE_MEDIA_ROOT = Path(os.environ.get('PRIVATE_MEDIA_ROOT', BASE_DIR / 'private_media'))
LOGIN_URL = 'two_factor:login'
LOGIN_REDIRECT_URL = '/teacher/'
LOGOUT_REDIRECT_URL = '/login/'
TWO_FACTOR_PATCH_ADMIN = False
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
if not DEBUG and SECRET_KEY == 'development-only-not-for-production':
    raise RuntimeError('DJANGO_SECRET_KEY is required outside development')

ACCESS_CODE_HMAC_KEYS = {1: os.environ.get('ACCESS_CODE_HMAC_KEY', 'local-access-code-key')}
RATE_LIMIT_HMAC_KEY = os.environ.get('RATE_LIMIT_HMAC_KEY', 'local-rate-limit-key')
if not DEBUG and ('ACCESS_CODE_HMAC_KEY' not in os.environ or 'RATE_LIMIT_HMAC_KEY' not in os.environ):
    raise RuntimeError('Access-code and rate-limit keys are required')
MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1, 'apps.accounts.middleware.SessionValidityMiddleware')

# Upload limits for large batch exam imports (up to 2,500 files / 100 MB total)
DATA_UPLOAD_MAX_NUMBER_FILES = 2500
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024

