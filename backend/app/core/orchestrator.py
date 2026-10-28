from app.agents.web_scraper.agent import ScraperAgent

AGENT_TYPES = {"web_scraper": ScraperAgent}


def build_agent(agent_type, *args, **kwargs):
    if agent_type not in AGENT_TYPES:
        raise ValueError("Unknown agent type")
    return AGENT_TYPES[agent_type](*args, **kwargs)
