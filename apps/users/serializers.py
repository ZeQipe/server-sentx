from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import User


class UserSerializer(serializers.ModelSerializer):
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
            "stripe_customer_id",
        ]
        read_only_fields = ["stripe_customer_id"]
        ref_name = "SentxUser"

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

    def update(self, instance, validated_data):
        # Handle password separately
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)

        # Handle other fields
        for attr, value in validated_data.items():
            if attr != "re_password":  # Skip re_password
                setattr(instance, attr, value)

        instance.save()
        return instance
