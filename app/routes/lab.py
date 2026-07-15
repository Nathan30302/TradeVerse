"""
Strategy Lab routes — plain-English setup testing (journal + demo).
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services.strategy_lab import run_strategy_lab

bp = Blueprint('lab', __name__, url_prefix='/lab')


@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """Describe a setup in English and score it against journal / demo trades."""
    result = None
    description = ''
    symbol = ''
    timeframe = ''
    mode = 'auto'

    if request.method == 'POST':
        description = (request.form.get('description') or '').strip()
        symbol = (request.form.get('symbol') or '').strip()
        timeframe = (request.form.get('timeframe') or '').strip()
        mode = (request.form.get('mode') or 'auto').strip().lower()
        if len(description) < 20:
            flash('Describe your setup in a bit more detail (at least a few sentences).', 'warning')
        else:
            result = run_strategy_lab(
                current_user.id,
                description,
                symbol=symbol,
                timeframe=timeframe,
                mode=mode,
            )

    return render_template(
        'lab/index.html',
        result=result,
        description=description,
        symbol=symbol,
        timeframe=timeframe,
        mode=mode,
    )
