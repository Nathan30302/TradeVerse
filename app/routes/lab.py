"""
Strategy Lab routes — plain-English setup testing (journal + demo).
"""

from __future__ import annotations

from flask import Blueprint, flash, render_template, request
from flask_login import current_user, login_required

from app.services.strategy_lab import (
    CONCEPT_LABELS,
    LAB_GLOSSARY,
    LAB_PRESETS,
    run_strategy_lab,
)

bp = Blueprint('lab', __name__, url_prefix='/lab')


@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """Describe a setup in English and score it against journal / demo trades."""
    result = None
    description = (request.args.get('description') or '').strip()
    symbol = (request.args.get('symbol') or '').strip()
    timeframe = (request.args.get('timeframe') or '').strip() or '15M'
    mode = (request.args.get('mode') or 'auto').strip().lower() or 'auto'
    from_buddy = (request.args.get('from') or '').strip().lower() == 'ai'

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

    suggested_focus = ''
    if result and isinstance(result, dict):
        wr = float((result.get('stats') or {}).get('win_rate') or 0)
        concepts = ((result.get('rules') or {}).get('concepts') or [])[:3]
        concept_bits = ', '.join(str(c).replace('_', ' ') for c in concepts) if concepts else 'this setup'
        if wr >= 55:
            suggested_focus = f"Only trade {concept_bits} with planned R:R ≥ 1.5 (Lab win rate ~{wr:.0f}%)."
        else:
            suggested_focus = (
                f"Paper or skip {concept_bits} until journal edge improves "
                f"(Lab win rate ~{wr:.0f}%). Max 2 trades/day."
            )

    return render_template(
        'lab/index.html',
        result=result,
        description=description,
        symbol=symbol,
        timeframe=timeframe,
        mode=mode,
        presets=LAB_PRESETS,
        glossary=LAB_GLOSSARY,
        concept_labels=CONCEPT_LABELS,
        from_buddy=from_buddy,
        suggested_focus=suggested_focus,
    )
