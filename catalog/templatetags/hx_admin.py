from django import template

register = template.Library()


@register.filter
def photo_src(image) -> str:
    """Preview address for a product photo in the admin (uploaded file or pasted link)."""
    from catalog.admin import image_src
    return image_src(image.src) if image and image.src else ""
