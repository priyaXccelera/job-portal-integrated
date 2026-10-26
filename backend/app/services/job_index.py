"""Maintains jobs.search_vector (weighted full-text index).

Weights: title + required/preferred skills = A, company name = B,
description + responsibilities (HTML tags stripped) = C.
Neither function commits; the caller owns the transaction.
"""

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_UPDATE_SQL = """
UPDATE jobs AS j
SET search_vector =
      setweight(to_tsvector('english', coalesce(j.title, '')), 'A')
   || setweight(to_tsvector('english',
        coalesce(array_to_string(j.required_skills, ' '), '') || ' ' ||
        coalesce(array_to_string(j.preferred_skills, ' '), '')), 'A')
   || setweight(to_tsvector('english', coalesce(c.name, '')), 'B')
   || setweight(to_tsvector('english',
        regexp_replace(coalesce(j.description, '') || ' ' || coalesce(j.responsibilities, ''),
                       '<[^>]+>', ' ', 'g')), 'C')
FROM companies AS c
WHERE c.id = j.company_id
"""


def reindex_job(db: Session, job_id: uuid.UUID) -> None:
    """Rebuild search_vector for one job (flushes pending changes first; no commit)."""
    db.flush()
    db.execute(text(_UPDATE_SQL + " AND j.id = :job_id"), {"job_id": job_id})


def reindex_all(db: Session) -> int:
    """Rebuild search_vector for every job; returns number of rows updated (no commit)."""
    db.flush()
    result = db.execute(text(_UPDATE_SQL))
    count = result.rowcount or 0
    logger.info("Reindexed %d jobs", count)
    return count
