from django.db import transaction

from .models import AttachedFile


class AttachedFileService:
    """Service for handling attached files"""

    @staticmethod
    @transaction.atomic
    def attach_file(
        message, file, filename: str, content_type: str
    ) -> AttachedFile:
        """Attach a file to a message"""
        return AttachedFile.objects.create(
            message=message, file=file, filename=filename, content_type=content_type
        )
