"""A database-backed, restart-recoverable ticket processing queue.

The HTTP app runs jobs in a background task for the MVP. The job state itself
is durable, so a separate worker can claim the same table in a later deploy.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.core.config import settings
from app.models import Ticket, TicketProcessingJob, utc_now
from app.services.ticket_processor import process_ticket


logger = logging.getLogger(__name__)


def enqueue_ticket_processing(db: Session, ticket: Ticket) -> bool:
    job = db.scalar(
        select(TicketProcessingJob)
        .where(TicketProcessingJob.ticket_id == ticket.id)
        .with_for_update()
    )
    if job and job.status in {"pending", "running", "completed"}:
        return False
    if job and job.attempt_count >= settings.processing_max_attempts:
        return False
    if job:
        job.status = "pending"
        job.last_error = None
        job.started_at = None
        job.finished_at = None
    else:
        job = TicketProcessingJob(ticket_id=ticket.id, status="pending")
        db.add(job)
    ticket.status = "queued"
    return True


def run_ticket_processing_job(ticket_id: int) -> None:
    """Claim and execute exactly one queued ticket; safe to call repeatedly."""
    with SessionLocal() as db:
        job = db.scalar(
            select(TicketProcessingJob)
            .where(TicketProcessingJob.ticket_id == ticket_id)
            .with_for_update()
        )
        ticket = db.get(Ticket, ticket_id)
        if not job or not ticket or job.status != "pending":
            return
        job.status = "running"
        job.attempt_count += 1
        job.started_at = utc_now()
        ticket.status = "processing"
        db.commit()

    try:
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            if not ticket:
                return
            process_ticket(db, ticket)
            job = db.scalar(select(TicketProcessingJob).where(TicketProcessingJob.ticket_id == ticket_id).with_for_update())
            if job:
                job.status = "completed"
                job.last_error = None
                job.finished_at = utc_now()
                db.commit()
    except Exception as exc:
        logger.exception("Ticket processing job %s failed", ticket_id)
        with SessionLocal() as db:
            job = db.scalar(select(TicketProcessingJob).where(TicketProcessingJob.ticket_id == ticket_id).with_for_update())
            ticket = db.get(Ticket, ticket_id)
            if job:
                job.status = "failed"
                job.last_error = type(exc).__name__
                job.finished_at = utc_now()
            if ticket:
                ticket.status = "failed"
            db.commit()


def recover_unfinished_ticket_jobs() -> None:
    """Re-queue interrupted work during application startup."""
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(TicketProcessingJob).where(TicketProcessingJob.status.in_(["pending", "running"]))
            ).all()
        )
        for job in jobs:
            job.status = "pending"
        db.commit()
        ticket_ids = [job.ticket_id for job in jobs]
    for ticket_id in ticket_ids:
        run_ticket_processing_job(ticket_id)
