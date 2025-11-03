from django.db import models


class AnonymousUsageLimit(models.Model):
    fingerprint = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    session_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    ip_address = models.GenericIPAddressField()
    requests_made_today = models.IntegerField(default=0)
    last_reset_date = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ("fingerprint", "last_reset_date")
        indexes = [
            models.Index(fields=['fingerprint', 'last_reset_date'], name='anon_fp_date_idx'),
        ]

    def __str__(self) -> str:
        if self.fingerprint:
            return f"Anonymous usage for fingerprint {self.fingerprint[:8]}... on {self.last_reset_date}"
        return f"Anonymous usage for {self.ip_address} on {self.last_reset_date}"
