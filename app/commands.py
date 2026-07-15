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

    @app.cli.command('grant-promo-trial')
    @click.option('--days', default=60, show_default=True, help='Days of Pro Plus access from now')
    @click.option(
        '--only-active/--all-users',
        default=True,
        show_default=True,
        help='Limit to is_active users (default) or update every row',
    )
    def grant_promo_trial(days: int, only_active: bool):
        """
        Give existing accounts a fresh Pro Plus trial window (e.g. before paid billing).

        Sets subscription_tier=pro_plus, subscription_status=trialing, and
        trial_ends_at = now + days for each user. Keep TV_ALL_USERS_PROPLUS_TRIAL=1
        so the entitlements overlay stays aligned with the DB.
        """
        from app.models.user import User

        if days < 1 or days > 366:
            click.echo('days must be between 1 and 366')
            return

        now = datetime.now(timezone.utc)
        ends = now + timedelta(days=int(days))
        q = User.query
        if only_active:
            q = q.filter(User.is_active.is_(True))
        users = q.all()
        changed = 0
        for u in users:
            u.subscription_tier = 'pro_plus'
            u.subscription_status = 'trialing'
            u.trial_ends_at = ends
            # Clear paid expiry so promo trial is not overridden by an old stamp.
            try:
                u.subscription_expires_at = None
            except Exception:
                pass
            changed += 1
        if changed:
            db.session.commit()
        click.echo(
            f'Granted Pro Plus trial to {changed} user(s) until {ends.isoformat()} '
            f'({days} days). Ensure TV_ALL_USERS_PROPLUS_TRIAL=1 on the host.'
        )

    @app.cli.command('send-trial-reminders')
    @click.option(
        '--days-left',
        default='7,3,1',
        help='Comma-separated exact days remaining to notify (e.g. 7,3,1). Run daily via cron.',
    )
    def send_trial_reminders(days_left: str):
        """
        Email users whose Pro Plus trial hits specific \"days left\" milestones.

        Uses persisted trial_ends_at + subscription_status=trialing. Requires the same
        SMTP env vars as other mail commands (MAIL_USERNAME, MAIL_PASSWORD, sender).

        Schedule example (cron): 0 10 * * * cd /app && flask send-trial-reminders
        """
        from flask_mail import Message
        from app import mail
        from app.models.user import User

        sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')
        if not sender or not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
            click.echo('Mail not configured; skipping trial reminders.')
            return

        try:
            match_days = {int(x.strip()) for x in days_left.split(',') if x.strip()}
        except ValueError:
            click.echo('Invalid --days-left; use integers like 7,3,1')
            return

        now = datetime.now(timezone.utc)
        support = (current_app.config.get('SUPPORT_EMAIL') or 'tradeversesupport@gmail.com').strip()
        base_url = (current_app.config.get('PUBLIC_SITE_URL') or '').strip().rstrip('/')

        users = User.query.filter(
            User.is_active.is_(True),
            User.email.isnot(None),
            User.email != '',
            User.subscription_status == 'trialing',
            User.trial_ends_at.isnot(None),
        ).all()

        sent = 0
        for u in users:
            end = u.trial_ends_at
            if end is None:
                continue
            if getattr(end, 'tzinfo', None) is None:
                end = end.replace(tzinfo=timezone.utc)
            else:
                end = end.astimezone(timezone.utc)
            left = max(0, (end - now).days)
            if left not in match_days:
                continue

            msg = Message(
                subject=f'TradeVerse: {left} day{"s" if left != 1 else ""} left on your Pro Plus trial',
                sender=sender,
                recipients=[u.email],
            )
            lines = [
                f'Hi {u.username},',
                '',
                f'Your TradeVerse Pro Plus trial has {left} day{"s" if left != 1 else ""} remaining '
                f'(ends {end.strftime("%b %d, %Y")}).',
                '',
                'If you want help getting the most from your journal, reply to this email or write to '
                f'{support}.',
                '',
            ]
            if base_url:
                lines.append(f'Open TradeVerse: {base_url}')
                lines.append('')
            lines.append('— TradeVerse')
            msg.body = '\n'.join(lines)
            try:
                mail.send(msg)
                sent += 1
            except Exception:
                continue

        click.echo(f'Sent {sent} trial reminder(s).')

    @app.cli.command('admin-timed-link')
    @click.option(
        '--base-url',
        default='',
        help='Site origin, e.g. https://tradeverse.example.com (defaults to http://localhost:5000)',
    )
    def admin_timed_link_cmd(base_url: str):
        """Print a short-lived /admin/stats?admin_ts=… URL (signed with SECRET_KEY)."""
        from app.services.admin_console_support import generate_admin_ts_token

        tok = generate_admin_ts_token(current_app)
        base = (base_url or '').strip().rstrip('/') or 'http://localhost:5000'
        click.echo(f'{base}/admin/stats?admin_ts={tok}')
        click.echo(
            f'(Expires in {current_app.config.get("ADMIN_TIMED_LINK_MAX_AGE", 3600)} seconds.)'
        )

    return None
