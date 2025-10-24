from django.db import models


class Feedback(models.Model):
    message = models.OneToOneField(
        "chat_messages.Message", on_delete=models.CASCADE, related_name="feedback"
    )
    is_liked = models.BooleanField(null=True, blank=True)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Feedback on {self.message}"
