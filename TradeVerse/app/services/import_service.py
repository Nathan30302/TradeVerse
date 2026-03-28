"""
Import service: persist parsed imports into DB and enqueue ImportJob entries.
This module provides helpers used by routes and the worker.
"""
from app import db
from app.models.broker import ImportedTradeSource, ImportJob
from app.models.trade import Trade
from datetime import datetime
import os
import json


def create_import_source(user_id, broker_id, filename, source_type):
    src = ImportedTradeSource(user_id=user_id, broker_id=broker_id, filename=filename, source_type=source_type)
    db.session.add(src)
    db.session.commit()
    return src


def enqueue_import_job(user_id, broker_id, source_id, job_type, payload):
    job = ImportJob(user_id=user_id, broker_id=broker_id, source_id=source_id, job_type=job_type, payload=payload)
    db.session.add(job)
    db.session.commit()

    # If Redis is configured, enqueue an RQ background job for processing (preferred for production)
    redis_url = os.environ.get('REDIS_URL') or os.environ.get('RQ_REDIS_URL')
    if redis_url:
        try:
            from rq import Queue
            from redis import Redis
            from app.tasks.import_tasks import process_import_job

            redis_conn = Redis.from_url(redis_url)
            q = Queue('imports', connection=redis_conn)
            q.enqueue(process_import_job, job.id)
        except Exception:
            # If RQ not available or enqueue fails, leave the DB job for the fallback worker
            pass

    return job


def persist_parsed_trades(parsed_result, user_id, broker_id, source_id=None):
    """Persist parsed trades (list of rows) into the Trade model and link to ImportedTradeSource.
    parsed_result expected format: {'parsed': [ { 'raw': {...}, 'mapped_symbol': 'EURUSD', ... }, ... ], 'errors': [...]}
    This function tries to map common fields to Trade.
    """
    saved = []
    for row in parsed_result.get('parsed', []):
        raw = row.get('raw', {})
        symbol = row.get('mapped_symbol') or raw.get('symbol') or raw.get('Symbol') or raw.get('SYMBOL')
        action = (raw.get('action') or raw.get('Action') or raw.get('type') or raw.get('Side') or '').upper()
        # Normalize buy/sell
        trade_type = 'BUY' if action in ('BUY', 'B') else 'SELL' if action in ('SELL', 'S') else 'BUY'
        try:
            size = float(raw.get('size') or raw.get('Size') or raw.get('volume') or raw.get('Volume') or 0)
        except Exception:
            size = 0
        try:
            price = float(raw.get('price') or raw.get('Price') or raw.get('open') or raw.get('entry') or 0)
        except Exception:
            price = 0
        try:
            exit_price = raw.get('exit_price') or raw.get('close') or raw.get('exit')
            exit_price = float(exit_price) if exit_price else None
        except Exception:
            exit_price = None
        try:
            profit_loss = float(raw.get('profit_loss') or raw.get('Profit') or raw.get('profit') or 0)
        except Exception:
            profit_loss = None

        trade = Trade(
            user_id=user_id,
            symbol=symbol or 'UNKNOWN',
            trade_type=trade_type,
            lot_size=max(size, 0.0) or 1.0,
            entry_price=price or 0.0,
            exit_price=exit_price,
            profit_loss=profit_loss,
            broker=broker_id,
            trade_id=str(raw.get('trade_id') or raw.get('Order') or raw.get('order_id') or '')
        )
        # Try to infer entry_date
        try:
            dt = raw.get('date') or raw.get('Date') or raw.get('datetime')
            if dt:
                # try ISO parse, fallback to leave None
                try:
                    trade.entry_date = datetime.fromisoformat(dt)
                except Exception:
                    pass
        except Exception:
            pass

        db.session.add(trade)
        saved.append(trade)
    db.session.commit()

    # Associate saved trades with source_id if provided
    if source_id:
        for t in saved:
            try:
                t.imported_source_id = source_id
            except Exception:
                pass
        db.session.commit()

    # Optionally link trades to source via source_id stored in trade.post_trade_notes or another mechanism
    # Could be improved to have a proper FK from trades -> imported_trade_sources
    return saved
