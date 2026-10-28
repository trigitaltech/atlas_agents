from fastapi import HTTPException
from app.models.entities import Agent, Job


def require(db, model, id):
    row = db.get(model, id)
    if row is None:
        raise HTTPException(404, "Resource not found")
    return row


def serialize(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
