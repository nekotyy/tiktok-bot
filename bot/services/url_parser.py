"""URL parsing and validation for TikTok links."""

import re
from typing import Optional
from urllib.parse import urlparse


class URLParser:
    """Parser for TikTok URLs."""
    
    # TikTok URL patterns
    TIKTOK_PATTERNS = [
        r'https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s]+',
        r'https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+',
    ]
    
    # Supported TikTok domains
    TIKTOK_DOMAINS = [
        'tiktok.com',
        'www.tiktok.com',
        'm.tiktok.com',
        'vm.tiktok.com',
        'vt.tiktok.com',
    ]
    
    @classmethod
    def extract_tiktok_url(cls, text: str) -> Optional[str]:
        """Extract TikTok URL from text.
        
        Args:
            text: Text that may contain TikTok URL
            
        Returns:
            TikTok URL if found, None otherwise
        """
        if not text:
            return None
        
        # Try each pattern
        for pattern in cls.TIKTOK_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                url = match.group(0)
                # Clean up URL (remove trailing punctuation)
                url = url.rstrip('.,;:!?)]}')
                return url
        
        return None
    
    @classmethod
    def is_valid_tiktok_url(cls, url: str) -> bool:
        """Check if URL is a valid TikTok URL.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid TikTok URL
        """
        if not url:
            return False
        
        try:
            parsed = urlparse(url)
            
            # Check scheme
            if parsed.scheme not in ['http', 'https']:
                return False
            
            # Check domain
            domain = parsed.netloc.lower()
            if not any(domain == d or domain.endswith('.' + d) for d in cls.TIKTOK_DOMAINS):
                return False
            
            # Check that path is not empty
            if not parsed.path or parsed.path == '/':
                return False
            
            return True
        except Exception:
            return False
    
    @classmethod
    def normalize_url(cls, url: str) -> str:
        """Normalize TikTok URL (remove unnecessary parameters).
        
        Args:
            url: TikTok URL
            
        Returns:
            Normalized URL
        """
        if not url:
            return url
        
        try:
            parsed = urlparse(url)
            # Keep only the base URL without query parameters for short links
            if parsed.netloc in ['vm.tiktok.com', 'vt.tiktok.com']:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return url
        except Exception:
            return url
    
    @classmethod
    def extract_and_validate(cls, text: str) -> Optional[str]:
        """Extract and validate TikTok URL from text.
        
        Args:
            text: Text that may contain TikTok URL
            
        Returns:
            Valid TikTok URL if found, None otherwise
        """
        url = cls.extract_tiktok_url(text)
        if url and cls.is_valid_tiktok_url(url):
            return cls.normalize_url(url)
        return None
