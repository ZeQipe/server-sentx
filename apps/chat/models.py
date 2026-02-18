import secrets

from django.db import models

from apps.ChatSessions.models import ChatSession


class SharedChat(models.Model):
    token = models.CharField(max_length=64, unique=True, db_index=True)
    chat_session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="shares"
    )
    title = models.CharField(max_length=5000, blank=True, default="")
    snapshot = models.JSONField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Share {self.token[:8]}... for session {self.chat_session_id}"
