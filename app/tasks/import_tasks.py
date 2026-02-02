"""
RQ tasks for processing import jobs.
These functions are intended to be enqueued by RQ and executed by rq worker processes.
"""
from app import db
from app.models.broker import ImportJob, ImportedTradeSource
from app.importers.csv_importer import parse_csv
from app.importers.mt5_parser import parse_mt5
from app.services.import_service import persist_parsed_trades
from datetime import datetime
import os
import time
from app import metrics as metrics

try:
    from rq import get_current_job
except Exception:
    def get_current_job():
        return None


def process_import_job(job_id):
    job = db.session.get(ImportJob, job_id)
    if not job:
        return {'error': 'job not found'}
    # Mark running
    job.status = 'running'
    job.started_at = datetime.utcnow()
    db.session.commit()

    try:
        payload = job.payload or {}
        job_type = job.job_type
        filepath = payload.get('filepath') if isinstance(payload, dict) else None
        parsed = {'parsed': [], 'errors': []}
        if job_type == 'csv' and filepath and os.path.exists(filepath):
            with open(filepath, 'rb') as fh:
                parsed = parse_csv(fh, broker_id=job.broker_id, dry_run=False)
        elif job_type == 'mt5' and filepath and os.path.exists(filepath):
            with open(filepath, 'rb') as fh:
                parsed = parse_mt5(fh, broker_id=job.broker_id, dry_run=False)
        else:
            parsed['errors'].append({'error': f'Unsupported job type {job_type} or missing file'})
        start_ts = time.time()
        # If running in RQ, update job meta periodically
        rq_job = get_current_job()
        if rq_job:
            rq_job.meta['progress'] = 0
            rq_job.save()

        saved = persist_parsed_trades(parsed, user_id=job.user_id, broker_id=job.broker_id, source_id=job.source_id)

        # Update ImportJob with saved count and errors
        job.status = 'done'
        job.finished_at = datetime.utcnow()
        # store a summary in the payload for quick access
        job.payload = (job.payload or {})
        job.payload['saved_count'] = len(saved)
        job.payload['errors'] = parsed.get('errors', [])
        db.session.commit()

        duration = time.time() - start_ts
        # record metrics
        try:
            metrics.record_job_saved(len(saved) if saved is not None else 0)
            metrics.observe_job_duration(duration)
        except Exception:
            pass

        if rq_job:
            rq_job.meta['progress'] = 100
            rq_job.meta['saved'] = len(saved)
            rq_job.meta['errors'] = parsed.get('errors', [])
            rq_job.save()

        return {'saved': len(saved), 'errors': parsed.get('errors', [])}
    except Exception as e:
        job.status = 'failed'
        job.error = str(e)
        job.finished_at = datetime.utcnow()
        db.session.commit()
        rq_job = get_current_job()
        if rq_job:
            rq_job.meta['failed'] = True
            rq_job.meta['error'] = str(e)
            rq_job.save()
        try:
            metrics.record_job_failed(1)
        except Exception:
            pass
        return {'error': str(e)}