import ollama

from config import config

_client = ollama.Client(host=config.OLLAMA_HOST)


def embed_text(text: str) -> list[float]:
    response = _client.embeddings(model=config.OLLAMA_EMBED_MODEL, prompt=text)
    return response["embedding"]
