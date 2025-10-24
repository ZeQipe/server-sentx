from .models import Feedback


class FeedbackService:
    """Service for handling message feedback"""

    @staticmethod
    def add_feedback(
        message, is_liked: bool | None = None, comment: str | None = None
    ) -> Feedback:
        """Add feedback to a message"""
        feedback, created = Feedback.objects.get_or_create(
            message=message, defaults={"is_liked": is_liked, "comment": comment}
        )

        if not created:
            feedback.is_liked = is_liked
            feedback.comment = comment
            feedback.save()

        return feedback
