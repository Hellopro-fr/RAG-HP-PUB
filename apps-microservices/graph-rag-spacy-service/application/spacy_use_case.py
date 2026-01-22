import spacy
import logging
from typing import List, Dict, Any

from app.config import settings


class SpacyUseCase:
    """Core logic for Spacy operations."""

    def __init__(self):
        logging.info(f"Loading Spacy model: {settings.SPACY_MODEL}")
        try:
            self.nlp = spacy.load(settings.SPACY_MODEL)
            logging.info("Spacy model loaded successfully.")
        except OSError:
            logging.info(f"Downloading Spacy model: {settings.SPACY_MODEL}")
            from spacy.cli import download

            download(settings.SPACY_MODEL)
            self.nlp = spacy.load(settings.SPACY_MODEL)

    def lemmatize(self, text: str) -> List[Dict[str, Any]]:
        doc = self.nlp(text)
        return [
            {
                "text": token.text,
                "lemma": token.lemma_,
                "pos": token.pos_,
                "is_stop": token.is_stop,
            }
            for token in doc
        ]

    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        doc = self.nlp(text)
        return [
            {
                "text": ent.text,
                "label": ent.label_,
                "start_char": ent.start_char,
                "end_char": ent.end_char,
            }
            for ent in doc.ents
        ]
