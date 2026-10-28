from app.api.schemas import JobResponse
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.agents.web_scraper.schemas import ScrapeRequest
from app.services.jobs import submit
from app.api.dependencies import serialize

router = APIRouter(prefix="/api/scraping/jobs", tags=["Scraping"])


@router.post("", status_code=202, response_model=JobResponse)
def create_job(body: ScrapeRequest, db: Session = Depends(get_db)):
    return serialize(submit(db, body))
