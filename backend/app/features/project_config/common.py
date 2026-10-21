import re

AGENTS, SKILLS, MCP = "agents", "skills", "mcp"


LAYOUT = (AGENTS, SKILLS, MCP)  # the folders Themis itself relies on: they cannot be renamed or deleted


AGENT_FILE = "agent.md"


SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class ConfigError(Exception):
    """A config file cannot be used. The message is meant for the person editing it."""
