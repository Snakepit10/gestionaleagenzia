from django import template
import re

register = template.Library()

@register.filter
def sub(value, arg):
    """Subtract the arg from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def extract_distinta_number(note):
    """Extract distinta number from movement notes."""
    if not note:
        return None
    
    # Pattern per estrarre "Distinta N° 123"
    pattern = r'Distinta N° (\d+)'
    match = re.search(pattern, note)
    
    if match:
        return match.group(1)
    
    return None