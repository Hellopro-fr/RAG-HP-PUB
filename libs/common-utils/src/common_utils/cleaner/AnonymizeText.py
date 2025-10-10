import re
import uuid

DOMAIN = "gmail.com"
PREFIX = "anonym"

def gen_email_uuid(prefix: str = PREFIX, domain: str = DOMAIN, truncate: int | None = 12) -> str:
    h = uuid.uuid4().hex  # 32 hex chars (0-9a-f)
    if truncate:
        h = h[:truncate]
    return f"{prefix}_{h.lower()}@{domain}"

class AnonymizeText:
    def anonymize_text(self,text: str) -> str:
        processed_text = text

        phone_pattern = r'(?<![\d/])(?: (?:(?:\+|00)\d{1,3}[-.\s]?)?(?:\(\d{1,5}\)[-.\s]?)?\d(?:[\d\s.-]{5,13}\d) )(?!:)'
        processed_text = re.sub(phone_pattern, "06 23 42 43 23", processed_text, flags=re.VERBOSE)

        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        random_email = gen_email_uuid(truncate=12)
        processed_text = re.sub(email_pattern, random_email, processed_text)
        
        page_number_pattern = r'Page\s*\d+\s*of\s*\d+\s*'
        processed_text = re.sub(page_number_pattern,"", processed_text)

        
        return processed_text


    def normalize_text(self,text: str) -> str:
        processed_text = text

        processed_text = re.sub(r'</?[a-zA-Z][a-zA-Z0-9_:-]*[^>]*>', '', processed_text)

        url_pattern = r'\b(?:https?|ftp):\/\/[^\s<>()]+(?:\([^\s<>()]*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’])|\bwww\.[^\s<>()]+(?:\([^\s<>()]*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’])'
        processed_text = re.sub(url_pattern, '', processed_text, flags=re.IGNORECASE)

        processed_text = re.sub(r' +', ' ', processed_text)
        processed_text = processed_text.strip()

        return processed_text
