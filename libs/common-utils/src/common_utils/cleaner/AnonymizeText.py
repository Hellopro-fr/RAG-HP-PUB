import re

class AnonymizeText:
    def anonymize_text(text: str) -> str:
        processed_text = text

        phone_pattern = r'(?<![\d/])(?: (?:(?:\+|00)\d{1,3}[-.\s]?)?(?:\(\d{1,5}\)[-.\s]?)?\d(?:[\d\s.-]{5,13}\d) )(?!:)'
        processed_text = re.sub(phone_pattern, "06 23 42 43 23", processed_text, flags=re.VERBOSE)

        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        processed_text = re.sub(email_pattern, "n.cruchon@gmail.com", processed_text)

        return processed_text


    def normalize_text(text: str) -> str:
        processed_text = text

        processed_text = re.sub(r'<[^>]+>', '', processed_text)

        url_pattern = r'\b(?:https?|ftp):\/\/[^\s<>()]+(?:\([^\s<>()]*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’])|\bwww\.[^\s<>()]+(?:\([^\s<>()]*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’])'
        processed_text = re.sub(url_pattern, '', processed_text, flags=re.IGNORECASE)

        processed_text = re.sub(r' +', ' ', processed_text)
        processed_text = processed_text.strip()

        return processed_text
