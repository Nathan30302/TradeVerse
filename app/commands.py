"""
Management command to build and maintain FTS search index.
Run: flask build-fts-index
"""
from flask import current_app
from app.models.instrument_fts import build_fts_index
import click


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

    return None
