"""Celery tasks: the hourly feed sync and the daily reminders."""

from __future__ import annotations

from hubra.core.modules import per_tenant_job
from hubra.core.tasks import celery_app

from . import services


@celery_app.task(name="hubra_teams.tasks.sync_feeds")
@per_tenant_job("teams")
def sync_feeds() -> dict:
    from hubra.core.extensions import db

    done = services.sync_all()
    db.session.commit()
    return done


@celery_app.task(name="hubra_teams.tasks.remind")
@per_tenant_job("teams")
def remind() -> int:
    from hubra.core.extensions import db

    sent = services.remind()
    db.session.commit()
    return sent
