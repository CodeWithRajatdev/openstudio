"""Background job status and cancellation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job, utcnow

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_dict(job: Job) -> dict:
    remaining = max(0, int(job.total or 0) - int(job.completed or 0) - int(job.failed or 0))
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "failed": job.failed,
        "remaining": remaining,
        "payload": job.payload,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.get("")
def list_jobs(db: Session = Depends(get_db)):
    jobs = list(db.scalars(select(Job).order_by(Job.created_at.desc()).limit(50)).all())
    return [_job_dict(j) for j in jobs]


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("pending", "running"):
        payload = dict(job.payload or {})
        payload["cancel_requested"] = True
        job.payload = payload
        job.status = "cancelled"
        job.updated_at = utcnow()
        db.commit()
        db.refresh(job)
    return _job_dict(job)
