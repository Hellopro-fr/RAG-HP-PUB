import re
def clean_product_description(text: str) -> str:
    if not text: return ""
    return re.sub(r'</?p>|</?b>', '', text)
