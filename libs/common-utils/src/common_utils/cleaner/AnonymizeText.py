import re
import uuid
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

DOMAIN = "gmail.com"
PREFIX = "anonym"

def gen_email_uuid(prefix: str = PREFIX, domain: str = DOMAIN, truncate: int | None = 12) -> str:
    h = uuid.uuid4().hex  # 32 hex chars (0-9a-f)
    if truncate:
        h = h[:truncate]
    return f"{prefix}_{h.lower()}@{domain}"

class AnonymizeText:
    def anonymize_text(self,text: str) -> str:

        random_email = gen_email_uuid(truncate=12)
        processed_text = self.presidio_anonymizer(text,random_email)
        
        page_number_pattern = r'Page\s*\d+\s*of\s*\d+\s*'
        processed_text = re.sub(page_number_pattern,"", processed_text)

        
        return processed_text

    def presidio_anonymizer(self,text: str,email: str) -> str:
        analyzer   = AnalyzerEngine()
        anonymizer = AnonymizerEngine()

        results = analyzer.analyze(text=text, entities=["PHONE_NUMBER", "EMAIL_ADDRESS"], language="en")

        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "06 23 42 43 23"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": email})
            }
        )

        return anonymized.text

    def normalize_text(self,text: str) -> str:
        processed_text = text

        processed_text = re.sub(r'</?[a-zA-Z][a-zA-Z0-9_:-]*[^>]*>', '', processed_text)

        url_pattern = r'\b(?:https?|ftp):\/\/[^\s<>()]+(?:\([^\s<>()]*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’])|\bwww\.[^\s<>()]+(?:\([^\s<>()]*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’])'
        processed_text = re.sub(url_pattern, '', processed_text, flags=re.IGNORECASE)

        processed_text = re.sub(r' +', ' ', processed_text)
        processed_text = processed_text.strip()

        return processed_text
