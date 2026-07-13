#!/usr/bin/env python3
"""One-off helper to tabify dashboard/ai.html."""
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "app/templates/dashboard/ai.html"
lines = path.read_text().splitlines(keepends=True)

i_weekly_focus = next(i for i, l in enumerate(lines) if "Your weekly focus" in l)
i_vars = next(i for i, l in enumerate(lines) if "Resolve all template variables" in l)
i_weekly_review = next(i for i, l in enumerate(lines) if "Weekly Coach Brief" in l)
i_talk = next(i for i, l in enumerate(lines) if "{# Talk to AI Buddy" in l)
i_endblock = next(i for i, l in enumerate(lines) if l.strip() == "{% endblock %}" and "extra" not in l)
i_cockpit_end = i_endblock - 1
while i_cockpit_end > 0 and lines[i_cockpit_end].strip() != "</div>":
    i_cockpit_end -= 1

head = "".join(lines[:i_weekly_focus])
setup = "".join(lines[i_weekly_focus:i_vars])
vars_block = "".join(lines[i_vars:i_weekly_review])
review = "".join(lines[i_weekly_review:i_talk])
chat = "".join(lines[i_talk:i_cockpit_end])

tabs_head = """
<div id="ai-page-root" class="mb-2"
     data-query-url="{{ url_for('dashboard.ai_query') }}"
     data-trade-doctor-url="{{ url_for('dashboard.trade_doctor_api') }}"
     data-pin-url="{{ url_for('dashboard.pin_ai_note_json') }}"
     data-focus-url="{{ url_for('dashboard.apply_weekly_focus_json') }}"
     data-voice="{{ (voice_summary or '') | e }}"
     data-username="{{ (current_user.username or '') | e }}"
     data-suggested-focus="{{ (suggested_weekly_focus or '') | e }}"
     data-currency="{{ (chart_currency_code or current_user.preferred_currency or 'USD')|e }}"
     data-fx="{{ fx_usd_to_preferred|default(1.0) }}">
<ul class="nav nav-pills tv-ai-tabs mb-4 gap-2" id="aiBuddyTabs" role="tablist">
  <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#ai-tab-today" type="button">Today</button></li>
  <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#ai-tab-review" type="button">Review</button></li>
  <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#ai-tab-setup" type="button">Coach setup</button></li>
</ul>
<div class="tab-content">
<div class="tab-pane fade show active" id="ai-tab-today" role="tabpanel">
<div class="tv-surface soft p-3 p-md-4 mb-4 tv-hud-panel">
  <div class="tv-section-title mb-2"><i class="fas fa-sun me-2 text-warning"></i> Morning briefing</div>
  {% for line in (morning_briefing.lines or []) %}<motion class="tv-morning-line small">{{ line }}</motion>{% else %}
  <p class="small tv-muted mb-0">Log closed trades to unlock a personalized briefing.</p>{% endfor %}
  {% if last_trade_insight %}<p class="mt-3 pt-3 border-top small mb-0"><span class="text-muted">Latest trade:</span> {{ last_trade_insight }}</p>{% endif %}
  {% if has_ai_web %}<p class="small tv-muted mt-2 mb-0"><i class="fas fa-sparkles"></i> Web coach (OpenAI) is active for chat.</p>{% endif %}
</div>
<div class="tv-surface soft p-3 p-md-4 mb-4 d-none" id="aiSuggestedFocus">
  <div class="d-flex flex-wrap align-items-center justify-content-between gap-2">
    <div><div class="fw-semibold mb-1">Suggested weekly focus</div><div class="small" id="aiSuggestedFocusText">{{ suggested_weekly_focus or '' }}</motion></div>
    <div class="d-flex gap-2">
      <button type="button" class="btn btn-sm btn-primary" id="useSuggestedFocusBtn">Use this rule</button>
      <button type="button" class="btn btn-sm btn-outline-secondary" id="suggestFocusBtn">Suggest again</button>
    </div>
  </div>
</div>
"""

setup = setup.replace("Pro Plus unlocks deeper AI insights", "Pro Plus unlocks the web coach (OpenAI)")
setup = setup.replace(
    "Upgrade to unlock richer weekly alerts, advanced behavioural patterns, and stronger “what to fix next” recommendations.",
    "Upgrade for conversational coaching with your journal context. The local coach stays on all plans.",
)
setup = setup.replace(
    "{% if sub.tier not in ['pro_plus', 'elite', 'owner'] %}",
    "{% if not has_ai_web %}",
)

review = review.replace(
    "{% if weekly_weaknesses %}",
    "{% if weekly_review.get('has_data') and weekly_weaknesses %}",
)
review = review.replace(
    "{% if weekly_recs %}",
    "{% if weekly_review.get('has_data') and weekly_recs %}",
)

def fix_html(s: str) -> str:
    return s.replace("<motion", "<div").replace("</motion>", "</motion>")

out = (
    fix_html(head)
    + fix_html(tabs_head)
    + fix_html(chat)
    + '</div>\n<div class="tab-pane fade" id="ai-tab-review" role="tabpanel">\n'
    + vars_block
    + fix_html(review)
    + '</motion>\n<div class="tab-pane fade" id="ai-tab-setup" role="tabpanel">\n'
    + fix_html(setup)
    + "</motion>\n</motion>\n</motion>\n</motion>\n{% endblock %}\n\n{% block extra_js %}\n"
    + '<script src="{{ url_for(\'static\', filename=\'js/ai-buddy.js\') }}"></script>\n'
    + "{% endblock %}\n"
)
out = out.replace("<motion", "<div").replace("</motion>", "</motion>")
out = out.replace("</motion>", "</motion>")
import re
out = re.sub(r"</motion>", "</div>", out)
out = re.sub(r"<motion(\s|>)", lambda m: "<motion" + m.group(1), out)
path.write_text(out)
print("Wrote", path)
