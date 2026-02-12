from django import template

register = template.Library()

@register.filter(name='getattr')
def get_attribute(obj, attr):
    """Surgical attribute getter for templates."""
    return getattr(obj, attr, None)

@register.filter
def get_display(obj, attr):
    """Surgical display value getter for choices."""
    display_method = f"get_{attr}_display"
    if hasattr(obj, display_method):
        return getattr(obj, display_method)()
    return getattr(obj, attr, None)

@register.filter
def get_class(value):
    """Return the class name as a string (Lowercased)"""
    if isinstance(value, bool):
        return 'bool'
    if hasattr(value, 'strftime'):
        if hasattr(value, 'hour'):
            return 'datetime'
        return 'date'
    return value.__class__.__name__.lower()
