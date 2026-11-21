import getpass
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.accounts.models import AuditEvent, User


class Command(BaseCommand):
    help = "Create or update the single OWNER (teacher) account safely."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--display-name", required=True)
        parser.add_argument("--password", default="")

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"].strip()
        display_name = options["display_name"].strip()
        password = options["password"] or getpass.getpass("Owner password: ")
        if len(password) < 10:
            raise CommandError("Owner password must be at least 10 characters.")
        existing = User.objects.filter(role=User.Role.OWNER).first()
        if existing and existing.username != username:
            raise CommandError(f"An OWNER account ({existing.username}) already exists.")
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"role": User.Role.OWNER, "display_name": display_name, "is_staff": True, "is_superuser": True},
        )
        user.role = User.Role.OWNER
        user.display_name = display_name
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.auth_epoch += 1
        user.save()
        AuditEvent.objects.create(actor=None, action="owner.create" if created else "owner.password.reset", target_type="user", target_id=user.id)
        self.stdout.write(f"OWNER ready: {user.username}. Log in at /teacher/login/ to set up TOTP.")
