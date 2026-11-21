from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from apps.accounts.models import AuditEvent, User


class Command(BaseCommand):
    help = "Operator recovery command: reset OWNER TOTP/backup devices and revoke all active sessions."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--reason", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        user = User.objects.select_for_update().filter(username=options["username"].strip(), role=User.Role.OWNER).first()
        if not user:
            raise CommandError("OWNER account not found.")
        reason = options["reason"].strip()
        if not reason:
            raise CommandError("Recovery reason is required.")
        TOTPDevice.objects.filter(user=user).delete()
        StaticDevice.objects.filter(user=user).delete()
        user.auth_epoch += 1
        user.save(update_fields=["auth_epoch", "updated_at"])
        AuditEvent.objects.create(actor=None, action="owner.mfa.reset", target_type="user", target_id=user.id, reason=reason)
        self.stdout.write(f"MFA reset and sessions revoked for {user.username}. Next login requires fresh TOTP setup.")
