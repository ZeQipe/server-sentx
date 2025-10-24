"""
Abfuscator: deterministic integer obfuscation using salted alphabet shuffling.
- URL-safe alphabet
- Stable per salt
- Optional minimum output length via left-padding with the first alphabet char
"""
from typing import Optional


class Abfuscator:
    """
    Port of TypeScript Abfuscator to Python.
    Provides deterministic integer obfuscation for IDs.
    """
    
    BASE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    
    @staticmethod
    def _hash_salt_to_32bit(salt: str) -> int:
        """FNV-1a 32-bit hash"""
        hash_val = 0x811C9DC5
        for char in salt:
            hash_val ^= ord(char)
            hash_val = (hash_val * 0x01000193) & 0xFFFFFFFF
        return hash_val if hash_val != 0 else 0x9E3779B9
    
    @staticmethod
    def _xorshift32(seed: int) -> int:
        """Simple PRNG for alphabet shuffling"""
        x = seed & 0xFFFFFFFF
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= (x >> 17) & 0xFFFFFFFF
        x ^= (x << 5) & 0xFFFFFFFF
        return x & 0xFFFFFFFF
    
    @staticmethod
    def _create_shuffled_alphabet(salt: str) -> str:
        """Create deterministic shuffled alphabet from salt"""
        if not salt:
            return Abfuscator.BASE_ALPHABET
        
        seed = Abfuscator._hash_salt_to_32bit(salt)
        chars = list(Abfuscator.BASE_ALPHABET)
        
        for i in range(len(chars) - 1, 0, -1):
            seed = Abfuscator._xorshift32(seed)
            r = abs(seed) / 0xFFFFFFFF
            j = int(r * (i + 1))
            chars[i], chars[j] = chars[j], chars[i]
        
        return ''.join(chars)
    
    @staticmethod
    def _encode_base_n(num: int, alphabet: str) -> str:
        """Encode integer to base-N string using alphabet"""
        if not isinstance(num, int) or num < 0:
            raise ValueError("value must be a non-negative integer")
        if not alphabet or len(alphabet) < 2:
            raise ValueError("alphabet must have at least 2 characters")
        
        base = len(alphabet)
        if num == 0:
            return alphabet[0]
        
        n = num
        out = ""
        while n > 0:
            rem = n % base
            out = alphabet[rem] + out
            n = n // base
        
        return out
    
    @staticmethod
    def _decode_base_n(string: str, alphabet: str) -> int:
        """Decode base-N string to integer using alphabet"""
        if not string:
            raise ValueError("value must be a non-empty string")
        
        base = len(alphabet)
        char_map = {char: idx for idx, char in enumerate(alphabet)}
        
        n = 0
        for char in string:
            if char not in char_map:
                raise ValueError(f"invalid character in input: {char}")
            n = n * base + char_map[char]
        
        return n
    
    @staticmethod
    def _generate_pad(salt: str, value: int, length: int, alphabet: str) -> str:
        """Generate deterministic padding"""
        if length <= 0:
            return ""
        
        seed = Abfuscator._hash_salt_to_32bit(f"{salt}:{value}")
        base = len(alphabet)
        out = ""
        
        for _ in range(length):
            seed = Abfuscator._xorshift32(seed)
            idx = seed % base
            out += alphabet[idx]
        
        return out
    
    @staticmethod
    def _format_with_hyphens(core: str) -> str:
        """Insert hyphens every 8 characters"""
        if len(core) <= 8:
            return core
        
        parts = []
        for i in range(0, len(core), 8):
            parts.append(core[i:i+8])
        
        return '-'.join(parts)
    
    @staticmethod
    def encode(salt: str, value: int, min_length: Optional[int] = None) -> str:
        """
        Encode integer to obfuscated string.
        
        Args:
            salt: Salt for alphabet shuffling
            value: Integer to encode
            min_length: Minimum output length (optional)
        
        Returns:
            Obfuscated string with optional hyphens
        """
        alphabet = Abfuscator._create_shuffled_alphabet(salt)
        payload = Abfuscator._encode_base_n(value, alphabet)
        
        if min_length and min_length > len(payload):
            # Embed payload length in header char
            header_char = alphabet[len(payload)]
            pad_len = max(0, min_length - (1 + len(payload)))
            pad = Abfuscator._generate_pad(salt, value, pad_len, alphabet)
            core = header_char + pad + payload
            return Abfuscator._format_with_hyphens(core)
        
        return Abfuscator._format_with_hyphens(payload)
    
    @staticmethod
    def decode(salt: str, value: str) -> int:
        """
        Decode obfuscated string to integer.
        
        Args:
            salt: Salt for alphabet shuffling
            value: Obfuscated string to decode
        
        Returns:
            Decoded integer
        """
        alphabet = Abfuscator._create_shuffled_alphabet(salt)
        
        if not value:
            raise ValueError("value must be a non-empty string")
        
        # Strip hyphen separators
        compact = value.replace('-', '')
        
        # Try to interpret first char as header with payload length
        if compact[0] in alphabet:
            header_idx = alphabet.index(compact[0])
            payload_len = header_idx
            remaining = len(compact) - 1
            
            if payload_len > 0 and payload_len <= remaining:
                payload = compact[-payload_len:]
                return Abfuscator._decode_base_n(payload, alphabet)
        
        # Fallback: treat entire string as payload (no header/padding)
        return Abfuscator._decode_base_n(compact, alphabet)
