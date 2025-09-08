from app.core.embedding.Embedding import Embedding
import random

def generate_long_text(length_in_words):
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur",
             "adipiscing", "elit", "sed", "do", "eiusmod", "tempor",
             "incididunt", "ut", "labore", "et", "dolore", "magna", "aliqua"]
    text = []
    for _ in range(length_in_words):
        text.append(random.choice(words))
    return " ".join(text)


def test_chunking_text():
  text = generate_long_text(200000)

  embedding_service = Embedding()

  chunking = embedding_service._create_chunks(text,"autre")

  for data in chunking:
    assert len(data) <= 512
