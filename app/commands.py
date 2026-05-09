"""
Management command to build and maintain FTS search index.
Run: flask build-fts-index
"""
from flask import current_app
from app.models.instrument_fts import build_fts_index
import click
from datetime import datetime, timedelta, timezone
from app import db


def register_commands(app):
    """Register Flask CLI commands on the given app instance."""

    @app.cli.command('build-fts-index')
    def build_fts_command():
        """Build or rebuild the FTS5 search index for instruments."""
        click.echo("Building FTS5 search index...")
        success = build_fts_index()
        if success:
            click.echo("✓ FTS index built successfully")
        else:
            click.echo("✗ Failed to build FTS index")

    @app.cli.command('run-import-worker')
    @click.option('--once', is_flag=True, help='Process a single job then exit')
    def run_import_worker(once):
        """Run the background import worker which polls the DB for import jobs."""
        click.echo('Starting import worker (press CTRL+C to stop)')
        from app.worker import run_worker
        run_worker(loop=not once)

    @app.cli.command('send-weekly-summaries')
    @click.option('--days', default=7, help='Lookback window in days')
    def send_weekly_summaries(days: int):
        """
        Send a simple weekly performance email summary to all users.

        This is safe to run manually or via a scheduler. If mail is not configured,
        it prints a warning and exits successfully.
        """
        from flask_mail import Message
        from app import mail, db
        from app.models.user import User
        from app.models.trade import Trade

        mail_username = current_app.config.get('MAIL_USERNAME')
        mail_password = current_app.config.get('MAIL_PASSWORD')
        sender = current_app.config.get('WEEKLY_SUMMARY_SENDER')
        if not (mail_username and mail_password and sender):
            click.echo('Mail not configured; skipping weekly summaries.')
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        users = User.query.filter_by(is_active=True).all()
        sent = 0
        for u in users:
            trades = Trade.query.filter(
                Trade.user_id == u.id,
                Trade.status == 'CLOSED',
                Trade.exit_date.isnot(None),
                Trade.exit_date >= cutoff,
                Trade.profit_loss.isnot(None),
            ).all()
            total_pnl = sum((t.profit_loss or 0.0) for t in trades)
            wins = len([t for t in trades if (t.profit_loss or 0) > 0])
            losses = len([t for t in trades if (t.profit_loss or 0) < 0])
            total = wins + losses
            win_rate = (wins / total * 100) if total else 0.0

            msg = Message(
                subject=f'TradeVerse Weekly Summary ({days}d)',
                sender=sender,
                recipients=[u.email],
            )
            msg.body = (
                f'Hi {u.username},\n\n'
                f'Here is your last {days} days performance:\n'
                f'- Trades: {total}\n'
                f'- Win rate: {win_rate:.1f}%\n'
                f'- Net P/L: {total_pnl:.2f} {u.preferred_currency}\n\n'
                'Log in to TradeVerse to see deeper analytics.\n'
            )
            try:
                mail.send(msg)
                sent += 1
            except Exception:
                continue
        click.echo(f'Sent {sent} weekly summaries.')

    @app.cli.command('send-nudges')
    @click.option('--inactive-days', default=7, help='Nudge users inactive for N days')
    def send_nudges(inactive_days: int):
        """
        Send a short encouragement email to inactive users.

        This is safe to run manually or via a scheduler (Render cron, GitHub Actions, etc).
        If mail is not configured, it exits successfully.
        """
        from flask_mail import Message
        from app import mail
        from app.models.user import User

        sender = current_app.config.get('NUDGE_SENDER') or current_app.config.get('MAIL_DEFAULT_SENDER')
        if not sender or not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
            click.echo('Mail not configured; skipping nudges.')
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=int(inactive_days))
        users = User.query.filter_by(is_active=True).all()
        sent = 0
        for u in users:
            last = u.last_login or u.created_at
            if not last:
                continue
            last_aware = last.replace(tzinfo=timezone.utc) if getattr(last, 'tzinfo', None) is None else last.astimezone(timezone.utc)
            if last_aware >= cutoff:
                continue
            if not u.email:
                continue

            msg = Message(
                subject='TradeVerse: quick check-in',
                sender=sender,
                recipients=[u.email],
            )
            msg.body = (
                f'Hi {u.username},\n\n'
                'Quick check-in from TradeVerse.\n\n'
                'If you’ve been trading, take 2 minutes to log your last trade — it helps you spot patterns and improve faster.\n\n'
                'See you inside,\n'
                'TradeVerse\n'
            )
            try:
                mail.send(msg)
                sent += 1
            except Exception:
                continue

        click.echo(f'Sent {sent} nudges.')

    @app.cli.command('enforce-trial-expiry')
    def enforce_trial_expiry():
        """Downgrade expired trials to Free."""
        from app.models.user import User

        now = datetime.now(timezone.utc)
        users = User.query.filter(
            User.subscription_status == 'trialing',
            User.trial_ends_at.isnot(None),
            User.trial_ends_at < now,
        ).all()
        changed = 0
        for u in users:
            u.subscription_tier = 'free'
            u.subscription_status = 'expired'
            changed += 1
        if changed:
            db.session.commit()
        click.echo(f'Downgraded {changed} expired trials.')

    return None
