from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.chat.models import SharedChat


class Command(BaseCommand):
    help = "Delete shared chat snapshots older than 30 days"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Max age in days (default: 30)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show how many would be deleted",
        )

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)

        qs = SharedChat.objects.filter(created_at__lt=cutoff)
        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} snapshots older than {days} days")
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} snapshots older than {days} days"))
