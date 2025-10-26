from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import User


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer для создания пользователя (регистрация)"""
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    re_password = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(
        required=True, validators=[UniqueValidator(queryset=User.objects.all())]
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
            "re_password",
            "name",
        ]
        read_only_fields = ["id"]
        ref_name = "SentxUserCreate"

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("re_password"):
            raise serializers.ValidationError(
                {"non_field_errors": ["Passwords do not match."]}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("re_password")
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            name=validated_data.get("name", ""),
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    """Serializer для получения и обновления пользователя"""
    email = serializers.EmailField(
        required=False, validators=[UniqueValidator(queryset=User.objects.all())]
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "is_unlimited",
            "date_joined",
            "is_active",
            "stripe_customer_id",
            "google_id",
            "icloud_id",
            "x_id",
        ]
        read_only_fields = [
            "id",
            "date_joined",
            "stripe_customer_id",
            "google_id",
            "icloud_id",
            "x_id",
            "is_unlimited",
            "is_active",
        ]
        ref_name = "SentxUser"

    def update(self, instance, validated_data):
        # Обновляем только разрешенные поля
        for attr, value in validated_data.items():
            # Только email и name можно обновлять
            if attr in ['email', 'name']:
                setattr(instance, attr, value)

        instance.save()
        return instance
