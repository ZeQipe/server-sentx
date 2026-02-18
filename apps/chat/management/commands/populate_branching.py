from django.core.management.base import BaseCommand

from apps.ChatSessions.models import ChatSession
from apps.messages.models import Message


class Command(BaseCommand):
    help = "Populate parent/active_child/current_node for existing linear chats"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show what would be done",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        sessions = ChatSession.objects.all()
        total = sessions.count()
        updated = 0
        skipped = 0

        for session in sessions.iterator():
            if session.current_node_id is not None:
                skipped += 1
                continue

            messages = list(
                Message.objects.filter(chat_session=session).order_by("created_at")
            )
            if not messages:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(f"  Would link {len(messages)} messages in session {session.id}")
                updated += 1
                continue

            prev = None
            for msg in messages:
                msg.parent = prev
                msg.current_version = 1
                msg.total_versions = 1
                msg.save(update_fields=["parent", "current_version", "total_versions"])

                if prev is not None:
                    prev.active_child = msg
                    prev.save(update_fields=["active_child"])

                prev = msg

            session.current_node = messages[-1]
            session.save(update_fields=["current_node"])
            updated += 1

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}Done. Updated: {updated}, Skipped (already linked or empty): {skipped}, Total: {total}"
        ))
