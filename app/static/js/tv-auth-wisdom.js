/**
 * Rotating trading wisdom on login / register (reads #auth-wisdom-data).
 * Auto-advances on a fixed timer; progress bar fills left → right (no tap/skip).
 */
(function () {
    'use strict';

    function parseLines(raw) {
        try {
            var a = JSON.parse(raw || '[]');
            return Array.isArray(a) ? a.filter(function (s) { return s && String(s).trim(); }) : [];
        } catch (e) {
            return [];
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var dataEl = document.getElementById('auth-wisdom-data');
        var textEl = document.getElementById('authQuoteText');
        var bar = document.getElementById('authQuoteBar');
        var wrap = document.getElementById('authQuoteRotator');
        if (!dataEl || !textEl || !bar) return;

        var lines = parseLines(dataEl.getAttribute('data-lines'));
        if (!lines.length) return;

        var baseMs = parseInt(dataEl.getAttribute('data-interval') || '12000', 10) || 12000;
        var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var cycleMs = reduced ? Math.round(baseMs * 1.25) : baseMs;
        var idx = Math.floor(Math.random() * lines.length);
        var startTs = null;
        var raf = null;

        if (wrap) {
            wrap.style.cursor = 'default';
        }

        function show(i) {
            textEl.textContent = lines[i % lines.length];
        }

        function advance() {
            idx = (idx + 1) % lines.length;
            show(idx);
            startTs = null;
            bar.style.width = '0%';
        }

        function tick(ts) {
            if (!startTs) startTs = ts;
            var p = Math.min((ts - startTs) / cycleMs, 1);
            bar.style.width = (p * 100).toFixed(2) + '%';
            if (p >= 1) advance();
            raf = window.requestAnimationFrame(tick);
        }

        show(idx);
        raf = window.requestAnimationFrame(tick);
    });
})();
