#!/usr/bin/env python3
"""Restructure dashboard/ai.html for tabbed AI Buddy. Run from repo root."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "app/templates/dashboard/ai.html"
INSERT = ROOT / "scripts/ai_html_insert.txt"

SETUP_START = (
    '<motion class="tv-surface soft p-3 p-md-4 mb-4">'.replace("motion", "div")
)
SETUP_START = (
    '<div class="tv-surface soft p-3 p-md-4 mb-4">\n'
    '    <div class="tv-section-title mb-2"><i class="fas fa-bullseye me-2 text-primary"></i>Your weekly focus</div>'
)


def main():
    text = AI.read_text()

    text = text.replace(
        "{% if sub.tier not in ['pro_plus', 'elite', 'owner'] %}",
        "{% if not has_ai_web %}",
    )
    text = text.replace(
        "Pro Plus unlocks deeper AI insights",
        "Pro Plus unlocks the web coach (OpenAI)",
    )
    text = text.replace(
        "Upgrade to unlock richer weekly alerts, advanced behavioural patterns, and stronger “what to fix next” recommendations.",
        "Upgrade for conversational coaching with your journal context. The local coach remains on all plans.",
    )
    text = text.replace(
        "{% if weekly_weaknesses %}",
        "{% if weekly_review.get('has_data') and weekly_weaknesses %}",
    )
    text = text.replace(
        "{% if weekly_recs %}",
        "{% if weekly_review.get('has_data') and weekly_recs %}",
    )

    setup_end_marker = (
        "{% endif %}\n\n"
        "{# ------------------------------------------------------------------ #}\n"
        "{# Resolve all template variables once, safely, before rendering HTML #}\n"
        "{# ------------------------------------------------------------------ #}\n"
    )
    review_start_marker = (
        "{# ------------------------------------------------------------------ #}\n"
        "{# Weekly Review + Smart Alerts                                        #}\n"
        "{# ------------------------------------------------------------------ #}\n"
    )
    chat_start_marker = (
        "{# ------------------------------------------------------------------ #}\n"
        "{# Talk to AI Buddy                                                    #}\n"
        "{# ------------------------------------------------------------------ #}\n"
    )
    coach_anchor = (
        '            <a class="btn btn-primary" href="{{ url_for(\'trade.add\') }}">'
        '<i class="fas fa-plus-circle me-1"></i> Add Trade</a>\n'
        "        </div>\n"
        "    </div>\n"
        "</div>\n\n"
    )

    i_setup = text.find(SETUP_START)
    i_setup_end = text.find(setup_end_marker, i_setup)
    if i_setup < 0 or i_setup_end < 0:
        raise SystemExit("setup block markers not found")
    setup_block = text[i_setup:i_setup_end].rstrip() + "\n"
    text = text[:i_setup] + text[i_setup_end:]

    i_review = text.find(review_start_marker)
    i_chat = text.find(chat_start_marker)
    if i_review < 0 or i_chat < 0:
        raise SystemExit("review/chat markers not found")
    review_block = text[i_review:i_chat].rstrip() + "\n"
    text = text[:i_review] + text[i_chat:]

    i_chat2 = text.find(chat_start_marker)
    i_end = text.find("\n</div>\n{% endblock %}", i_chat2)
    if i_chat2 < 0 or i_end < 0:
        raise SystemExit("chat/end markers not found")
    chat_block = text[i_chat2:i_end].rstrip() + "\n"
    chat_block = chat_block.replace(
        '<div class="card border-0 mb-4 tv-surface tv-hud-panel">',
        '<div id="ai-chat-card" class="card border-0 mb-4 tv-surface tv-hud-panel">',
        1,
    )
    text = text[:i_chat2] + text[i_end:]

    head = INSERT.read_text()
    cut = head.find('<div id="ai-section-setup"')
    if cut >= 0:
        head = head[:cut].rstrip() + "\n"
    i_coach = text.find(coach_anchor)
    if i_coach < 0:
        raise SystemExit("coach mode anchor not found")
    insert_at = i_coach + len(coach_anchor)

    middle = (
        head
        + "\n"
        + chat_block
        + "\n</div>\n\n"
        + '<div id="ai-section-setup" class="ai-tab-panel d-none">\n'
        + setup_block
        + "</div>\n\n"
        + '<div id="ai-section-review" class="ai-tab-panel d-none">\n'
        + review_block
        + "</div>\n</div>\n"
    )

    text = text[:insert_at] + middle + text[insert_at:]

    text = re.sub(
        r"\n(?:</motion>\s*)+\n{% endblock %}".replace("motion", "div"),
        "\n</div>\n</div>\n{% endblock %}",
        text,
        count=1,
    )
    text = re.sub(
        r"\n(?:</div>\s*)+\n{% endblock %}",
        "\n</div>\n</div>\n{% endblock %}",
        text,
        count=1,
    )

    css_add = """
  .tv-ai-tabs .nav-link { border-radius: 999px; font-weight: 600; }
  .tv-ai-tabs .nav-link.active { background: var(--primary, #6366f1); color: #fff; }
  .tv-morning-line { padding: 0.35rem 0; border-bottom: 1px solid rgba(148,163,184,0.12); }
  .tv-morning-line:last-child { border-bottom: none; }
"""
    if "tv-ai-tabs" not in text:
        text = text.replace("</style>", css_add + "</style>", 1)

    js_start = text.find("{% block extra_js %}")
    if js_start >= 0:
        text = (
            text[:js_start]
            + "{% block extra_js %}\n"
            + "<script src=\"{{ url_for('static', filename='js/ai-buddy.js') }}\"></script>\n"
            + "{% endblock %}\n"
        )

    AI.write_text(text)
    print("OK:", AI, "lines", len(text.splitlines()))


if __name__ == "__main__":
    main()
