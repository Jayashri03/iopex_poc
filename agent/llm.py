import ollama

from config import config

_client = ollama.Client(host=config.OLLAMA_HOST)


def chat(messages: list[dict]) -> str:
    response = _client.chat(
        model=config.OLLAMA_CHAT_MODEL,
        messages=messages,
        options={"temperature": 0.1},
    )
    return response["message"]["content"]
