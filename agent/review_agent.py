from agent.reasoning import AgentResult, ReviewAgent
from agent.tools import build_tools
from config import config
from pexgit_adapter.base import PexGitAdapter, PullRequest


def review_pr(pr: PullRequest, adapter: PexGitAdapter) -> AgentResult:
    tools = build_tools(adapter)
    agent = ReviewAgent(tools=tools, max_steps=config.AGENT_MAX_STEPS)
    return agent.run(pr)
