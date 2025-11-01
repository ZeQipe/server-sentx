from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_unlimited = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    
    # SSE Session ID
    session_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    # Social authentication fields
    google_id = models.CharField(max_length=255, blank=True, null=True)
    icloud_id = models.CharField(max_length=255, blank=True, null=True)
    x_id = models.CharField(max_length=255, blank=True, null=True)

    # Payment fields
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)

    # Override the related_name for groups and user_permissions
    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="groups",
        blank=True,
        help_text="The groups this user belongs to.",
        related_name="custom_user_set",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name="user permissions",
        blank=True,
        help_text="Specific permissions for this user.",
        related_name="custom_user_set",
        related_query_name="user",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"

    def __str__(self):
        return self.email
