"""
Custom mixins for handling obfuscated IDs in ViewSets.
"""
from django.conf import settings
from rest_framework.exceptions import NotFound

from .abfuscator import Abfuscator


class ObfuscatedLookupMixin:
    """
    Mixin that allows ViewSets to lookup objects by obfuscated ID.
    Only deobfuscates when lookup_field is 'pk' or 'id'.
    """
    
    def get_object(self):
        """
        Override get_object to handle obfuscated IDs in URL.
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get the lookup value from URL
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)
        
        if lookup_value is None:
            raise NotFound("No ID provided")
        
        # Only deobfuscate if lookup_field is 'pk' or 'id'
        lookup_field = getattr(self, 'lookup_field', 'pk')
        should_deobfuscate = lookup_field in ('pk', 'id')
        
        if should_deobfuscate:
            # Try to deobfuscate if it's a string
            if isinstance(lookup_value, str) and not lookup_value.isdigit():
                try:
                    salt = settings.ABFUSCATOR_ID_KEY
                    lookup_value = Abfuscator.decode(salt=salt, value=lookup_value)
                except (ValueError, Exception):
                    raise NotFound(f"Invalid ID format: {lookup_value}")
            else:
                # Fallback for plain integers (backward compatibility)
                lookup_value = int(lookup_value) if isinstance(lookup_value, str) else lookup_value
        
        # Perform the actual lookup
        filter_kwargs = {lookup_field: lookup_value}
        
        try:
            obj = queryset.get(**filter_kwargs)
        except queryset.model.DoesNotExist:
            raise NotFound(f"No {queryset.model.__name__} found with this ID")
        
        # May raise a permission denied
        self.check_object_permissions(self.request, obj)
        
        return obj
