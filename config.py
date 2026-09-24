import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "pr_review_agent")

    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5-coder:7b")

    AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))

    # Phase 1 assumption: a PR's full commit history (messages + diffs) is
    # passed to the agent in one shot, no RAG/retrieval. This is a rough
    # chars-not-tokens budget for that commit context specifically (it does
    # not include the system prompt or tool-loop overhead). PRs that exceed
    # it are flagged as needing batching/aggregation instead of silently
    # truncated - see agent/context_builder.py and README "Phase 2".
    MAX_COMMIT_CONTEXT_CHARS = int(os.getenv("MAX_COMMIT_CONTEXT_CHARS", "6000"))


config = Config()
