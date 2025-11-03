from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class ChatSession(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
        null=True,
        blank=True,
    )
    anonymous_user = models.ForeignKey(
        'anonymousUsageLimits.AnonymousUsageLimit',
        on_delete=models.CASCADE,
        related_name="chat_sessions",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=5000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.user:
            return f"{self.user.email} - {self.title or 'Untitled chat'}"
        elif self.anonymous_user:
            return f"Anonymous ({self.anonymous_user.fingerprint[:8] if self.anonymous_user.fingerprint else self.anonymous_user.ip_address}) - {self.title or 'Untitled chat'}"
        return f"Unknown user - {self.title or 'Untitled chat'}"
