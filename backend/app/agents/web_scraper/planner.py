from pydantic import BaseModel
from app.agents.web_scraper.schemas import ScrapeRequest


class Plan(BaseModel):
    strategy: str = (
        "Breadth-first authorized internal links; one evidence-backed record per page"
    )
    instruction: str
    fields: list[str]
    max_pages: int
    max_depth: int


def plan(request: ScrapeRequest) -> Plan:
    return Plan(
        instruction=request.instruction,
        fields=request.fields,
        max_pages=request.max_pages,
        max_depth=request.max_depth,
    )
