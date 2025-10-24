from django.db import models


class AnonymousUsageLimit(models.Model):
    ip_address = models.GenericIPAddressField()
    requests_made_today = models.IntegerField(default=0)
    last_reset_date = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ("ip_address", "last_reset_date")

    def __str__(self) -> str:
        return f"Anonymous usage for {self.ip_address} on {self.last_reset_date}"
