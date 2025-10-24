from django.db import models


class AttachedFile(models.Model):
    message = models.ForeignKey("messages.Message", on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="chat_files/")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.filename
