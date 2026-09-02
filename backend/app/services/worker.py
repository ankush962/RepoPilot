import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.models import CodeChunk, IndexJob, Repository
from app.services.git import current_remote_commit
from app.services.ingestion import index_repository
from app.services.vector_store import upsert_chunks


logger = logging.getLogger("repopilot.worker")


# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

# A job left in "running" longer than this is considered abandoned.
# This protects against worker crashes, machine restarts, SIGKILL,
# container termination, etc.

# ------------------------------------------------------------------
# STALE JOB RECOVERY
# ------------------------------------------------------------------

def recover_stale_jobs(db) -> int:
    cutoff = (
        datetime.utcnow()
        - timedelta(
            minutes=settings.stale_job_minutes
        )
    )

    stale_jobs = (
        db.query(IndexJob)
        .filter(
            IndexJob.status == "running",
            IndexJob.started_at.isnot(None),
            IndexJob.started_at < cutoff,
        )
        .all()
    )

    recovered = 0

    for job in stale_jobs:
        repository = db.get(
            Repository,
            job.repository_id,
        )

        if job.attempts < settings.max_index_attempts:
            job.status = "queued"
            job.stage = (
                f"Recovered after worker crash "
                f"({job.attempts}/"
                f"{settings.max_index_attempts})"
            )
            job.error = (
                "Previous worker stopped unexpectedly "
                "while processing this indexing job."
            )
            job.started_at = None

            if repository:
                repository.status = "indexing"

            logger.warning(
                "stale_index_job_recovered",
                extra={
                    "job_id": job.id,
                    "repository_id": job.repository_id,
                    "attempts": job.attempts,
                },
            )

        else:
            job.status = "failed"
            job.stage = (
                "Worker crash; retry limit reached"
            )
            job.error = (
                "Worker stopped unexpectedly and the "
                "maximum number of indexing attempts "
                "has been reached."
            )
            job.finished_at = datetime.utcnow()

            if repository:
                repository.status = "error"

            logger.error(
                "stale_index_job_failed",
                extra={
                    "job_id": job.id,
                    "repository_id": job.repository_id,
                    "attempts": job.attempts,
                },
            )

        recovered += 1

    if recovered:
        db.commit()

    return recovered


# ------------------------------------------------------------------
# JOB CLAIMING
# ------------------------------------------------------------------

def _claim_job(db):
    """
    Atomically claim one queued indexing job.

    FOR UPDATE SKIP LOCKED allows multiple workers to safely
    process jobs without claiming the same job.
    """
    row = db.execute(
        text(
            """
            SELECT id
            FROM index_jobs
            WHERE status = 'queued'
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )
    ).first()

    if not row:
        return None

    job = db.get(IndexJob, row.id)

    if not job:
        return None

    job.status = "running"
    job.started_at = datetime.utcnow()
    job.attempts += 1
    job.stage = "Starting"
    job.progress = 1

    db.commit()

    logger.info(
        "index_job_claimed",
        extra={
            "job_id": job.id,
            "repository_id": job.repository_id,
            "attempt": job.attempts,
        },
    )

    return job.id


# ------------------------------------------------------------------
# JOB PROCESSING
# ------------------------------------------------------------------

def process_job(job_id):
    db = SessionLocal()

    try:
        job = db.get(IndexJob, job_id)

        if not job:
            logger.warning(
                "index_job_not_found",
                extra={"job_id": job_id},
            )
            return

        # A recovered/queued job may theoretically be claimed after
        # another worker has already changed its state. Avoid doing
        # work unless this job is actually running.
        if job.status != "running":
            logger.warning(
                "index_job_not_running",
                extra={
                    "job_id": job_id,
                    "status": job.status,
                },
            )
            return

        repo = db.get(
            Repository,
            job.repository_id,
        )

        if not repo:
            job.status = "failed"
            job.error = "Repository not found"
            job.stage = "Repository not found"
            job.finished_at = datetime.utcnow()
            db.commit()

            logger.error(
                "index_job_repository_not_found",
                extra={
                    "job_id": job_id,
                    "repository_id": job.repository_id,
                },
            )

            return

        def progress(percent, stage):
            """
            Persist indexing progress so the API/frontend
            can display the current worker state.
            """
            job.progress = max(
                0,
                min(99, percent),
            )
            job.stage = stage
            db.commit()

        # ---------------------------------------------------------
        # STEP 1: Clone/update repository and create chunks
        # ---------------------------------------------------------

        progress(
            5,
            "Preparing repository",
        )

        result = index_repository(
            db,
            repo,
            progress=progress,
        )

        # Count the actual chunks currently stored for this repository.
        result_chunks = (
            db.query(CodeChunk)
            .filter(
                CodeChunk.repository_id == repo.id,
            )
            .count()
        )

        # ---------------------------------------------------------
        # STEP 2: Generate embeddings
        # ---------------------------------------------------------

        progress(
            72,
            "Generating embeddings",
        )

        chunks = (
            db.query(CodeChunk)
            .filter(
                CodeChunk.repository_id == repo.id,
                CodeChunk.embedding.is_(None),
            )
            .all()
        )

        if chunks:
            upsert_chunks(
                repo.id,
                chunks,
            )

        # Count all successfully embedded chunks.
        vectors = (
            db.query(CodeChunk)
            .filter(
                CodeChunk.repository_id == repo.id,
                CodeChunk.embedding.isnot(None),
            )
            .count()
        )

        # ---------------------------------------------------------
        # STEP 3: Finish job
        # ---------------------------------------------------------

        job.result_chunks = result_chunks
        job.result_vectors = vectors
        job.status = "completed"
        job.progress = 100
        job.stage = "Index ready"
        job.finished_at = datetime.utcnow()

        repo.status = "indexed"

        db.commit()

        logger.info(
            "index_job_completed",
            extra={
                "job_id": job_id,
                "repository_id": repo.id,
                "chunks": result_chunks,
                "vectors": vectors,
                "changed": (
                    result.get("changed")
                    if isinstance(result, dict)
                    else None
                ),
                "new_chunks": (
                    result.get("new_chunks", 0)
                    if isinstance(result, dict)
                    else 0
                ),
            },
        )

    except Exception as exc:
        logger.exception(
            "index_job_failed",
            extra={"job_id": job_id},
        )

        try:
            job = db.get(
                IndexJob,
                job_id,
            )

            if job:
                job.error = str(exc)[:4000]

                if job.attempts < settings.max_index_attempts:
                    # Retry the job.
                    job.status = "queued"
                    job.stage = (
                        f"Retry scheduled "
                        f"({job.attempts}/"
                        f"{settings.max_index_attempts})"
                    )

                    # Clear started_at so the next attempt can get
                    # a fresh start timestamp.
                    job.started_at = None

                    retry_repo = db.get(
                        Repository,
                        job.repository_id,
                    )

                    if retry_repo:
                        retry_repo.status = "indexing"

                    logger.warning(
                        "index_job_retry_scheduled",
                        extra={
                            "job_id": job_id,
                            "attempt": job.attempts,
                            "max_attempts": (
                                settings.max_index_attempts
                            ),
                        },
                    )

                else:
                    # Retries exhausted.
                    job.status = "failed"
                    job.stage = "Indexing failed"
                    job.finished_at = datetime.utcnow()

                    failed_repo = db.get(
                        Repository,
                        job.repository_id,
                    )

                    if failed_repo:
                        failed_repo.status = "error"

                    logger.error(
                        "index_job_retries_exhausted",
                        extra={
                            "job_id": job_id,
                            "attempts": job.attempts,
                        },
                    )

                db.commit()

        except Exception:
            logger.exception(
                "index_job_failure_update_failed",
                extra={"job_id": job_id},
            )
            db.rollback()

    finally:
        db.close()


# ------------------------------------------------------------------
# GIT AUTO SYNC
# ------------------------------------------------------------------

def _enqueue_updated_repositories(db):
    """
    Detect repositories whose remote branch has moved ahead
    of the last indexed commit and enqueue an indexing job.

    Only repositories that already have a local clone and are
    currently indexed are checked.
    """
    if not settings.git_auto_sync_enabled:
        return

    repositories = (
        db.query(Repository)
        .filter(
            Repository.local_path.isnot(None),
            Repository.status == "indexed",
        )
        .all()
    )

    for repo in repositories:
        try:
            remote_commit = current_remote_commit(
                repo.local_path,
                repo.branch,
            )

            # Nothing changed since the last successful index.
            if remote_commit == repo.last_indexed_commit:
                continue

            # Avoid creating duplicate jobs.
            active = (
                db.query(IndexJob)
                .filter(
                    IndexJob.repository_id == repo.id,
                    IndexJob.status.in_(
                        [
                            "queued",
                            "running",
                        ]
                    ),
                )
                .first()
            )

            if active:
                continue

            job = IndexJob(
                repository_id=repo.id,
                stage="Git update detected",
                progress=0,
            )

            db.add(job)

            repo.status = "indexing"

            db.commit()

            logger.info(
                "git_update_detected",
                extra={
                    "repository_id": repo.id,
                    "old_commit": repo.last_indexed_commit,
                    "new_commit": remote_commit,
                    "branch": repo.branch,
                    "job_id": job.id,
                },
            )

        except Exception:
            logger.exception(
                "git_auto_sync_failed",
                extra={
                    "repository_id": repo.id,
                    "branch": repo.branch,
                },
            )


# ------------------------------------------------------------------
# WORKER LOOP
# ------------------------------------------------------------------

def run_worker():
    """
    Continuously:

    1. Recover stale jobs abandoned by crashed workers.
    2. Check GitHub for repository updates.
    3. Queue indexing jobs for changed repositories.
    4. Claim queued indexing jobs atomically.
    5. Process jobs.
    6. Sleep when there is no work.
    """
    logger.info(
        "RepoPilot index worker started"
    )

    last_git_sync = 0.0
    last_stale_recovery = 0.0

    # Recover stale jobs immediately when the worker starts.
    recovery_db = SessionLocal()

    try:
        recovered = recover_stale_jobs(
            recovery_db
        )

        if recovered:
            logger.warning(
                "startup_stale_job_recovery_complete",
                extra={
                    "recovered_jobs": recovered,
                },
            )

    except Exception:
        logger.exception(
            "startup_stale_job_recovery_failed"
        )

    finally:
        recovery_db.close()

    last_stale_recovery = time.monotonic()

    while True:
        now = time.monotonic()

        # ---------------------------------------------------------
        # STALE JOB RECOVERY
        # ---------------------------------------------------------

        # Run periodically in case a worker crashes while the
        # worker process itself stays alive.
        recovery_interval = min(
            max(
                settings.worker_poll_seconds,
                30,
            ),
            300,
        )

        if now - last_stale_recovery >= recovery_interval:
            recovery_db = SessionLocal()

            try:
                recovered = recover_stale_jobs(
                    recovery_db
                )

                if recovered:
                    logger.warning(
                        "periodic_stale_job_recovery_complete",
                        extra={
                            "recovered_jobs": recovered,
                        },
                    )

            except Exception:
                logger.exception(
                    "periodic_stale_job_recovery_failed"
                )

            finally:
                recovery_db.close()

            last_stale_recovery = now

        # ---------------------------------------------------------
        # GIT AUTO-SYNC POLL
        # ---------------------------------------------------------

        if (
            settings.git_auto_sync_enabled
            and (
                now - last_git_sync
                >= settings.git_auto_sync_interval_seconds
            )
        ):
            sync_db = SessionLocal()

            try:
                _enqueue_updated_repositories(
                    sync_db
                )

            except Exception:
                logger.exception(
                    "git_auto_sync_poll_failed"
                )

            finally:
                sync_db.close()

            last_git_sync = now

        # ---------------------------------------------------------
        # INDEX JOB POLL
        # ---------------------------------------------------------

        db = SessionLocal()

        try:
            job_id = _claim_job(db)

        except Exception:
            logger.exception(
                "worker_poll_failed"
            )
            job_id = None

        finally:
            db.close()

        # ---------------------------------------------------------
        # PROCESS OR SLEEP
        # ---------------------------------------------------------

        if job_id:
            process_job(job_id)

        else:
            time.sleep(
                settings.worker_poll_seconds
            )


if __name__ == "__main__":
    run_worker()
