from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UsageLimit(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="usage_limit"
    )
    free_requests_limit = models.IntegerField(default=10)
    paid_requests_limit = models.IntegerField(default=100)
    requests_made_today = models.IntegerField(default=0)
    last_reset_date = models.DateField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Usage limits for {self.user.email}"
