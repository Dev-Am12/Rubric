from django import template

from submissions.url_validation import safe_link


register = template.Library()


@register.filter(name='safe_link')
def safe_link_filter(value):
    return safe_link(value)
