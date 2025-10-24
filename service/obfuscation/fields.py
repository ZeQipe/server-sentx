"""
Custom serializer fields for ID obfuscation.
"""
from django.conf import settings
from rest_framework import serializers

from .abfuscator import Abfuscator


class ObfuscatedIDField(serializers.Field):
    """
    Custom field that obfuscates integer IDs on output and deobfuscates on input.
    """
    
    def __init__(self, **kwargs):
        # Don't force read_only=False if it's explicitly set
        super().__init__(**kwargs)
    
    def to_representation(self, value):
        """Convert integer ID to obfuscated string"""
        if value is None:
            return None
        
        salt = settings.ABFUSCATOR_ID_KEY
        return Abfuscator.encode(salt=salt, value=int(value), min_length=17)
    
    def to_internal_value(self, data):
        """Convert obfuscated string to integer ID"""
        if data is None:
            return None
        
        if isinstance(data, int):
            # If already an integer, return as is (for backward compatibility)
            return data
        
        if not isinstance(data, str):
            raise serializers.ValidationError("ID must be a string or integer")
        
        try:
            salt = settings.ABFUSCATOR_ID_KEY
            return Abfuscator.decode(salt=salt, value=data)
        except (ValueError, Exception) as e:
            raise serializers.ValidationError(f"Invalid obfuscated ID: {str(e)}")


class ObfuscatedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """
    Custom PrimaryKeyRelatedField that handles obfuscated IDs.
    """
    
    def to_representation(self, value):
        """Convert object to obfuscated ID"""
        if value is None:
            return None
        
        pk = value.pk
        salt = settings.ABFUSCATOR_ID_KEY
        return Abfuscator.encode(salt=salt, value=int(pk), min_length=17)
    
    def to_internal_value(self, data):
        """Convert obfuscated ID to object"""
        if data is None:
            return None
        
        # Try to deobfuscate if it's a string
        if isinstance(data, str):
            try:
                salt = settings.ABFUSCATOR_ID_KEY
                pk = Abfuscator.decode(salt=salt, value=data)
            except (ValueError, Exception):
                raise serializers.ValidationError(f"Invalid obfuscated ID: {data}")
        elif isinstance(data, int):
            # Backward compatibility: accept plain integers
            pk = data
        else:
            raise serializers.ValidationError("ID must be a string or integer")
        
        # Use parent's logic to fetch the object
        try:
            return self.get_queryset().get(pk=pk)
        except self.queryset.model.DoesNotExist:
            self.fail('does_not_exist', pk_value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)
