/**
 * Rotating trading wisdom on login / register (reads #auth-wisdom-data).
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
        var nextBtn = document.getElementById('authQuoteNext');
        var wrap = document.getElementById('authQuoteRotator');
        if (!dataEl || !textEl || !bar) return;

        var lines = parseLines(dataEl.getAttribute('data-lines'));
        if (!lines.length) return;

        var baseMs = parseInt(dataEl.getAttribute('data-interval') || '16000', 10) || 16000;
        var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var idx = Math.floor(Math.random() * lines.length);
        var cycleMs = baseMs;
        var startTs = null;
        var raf = null;

        function pickCycle() {
            var b = reduced ? baseMs * 1.75 : baseMs;
            return Math.round(b * (0.82 + Math.random() * 0.36));
        }

        function show(i) {
            textEl.textContent = lines[i % lines.length];
        }

        function advance() {
            idx = (idx + 1) % lines.length;
            show(idx);
            cycleMs = pickCycle();
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

        if (nextBtn) {
            nextBtn.addEventListener('click', function (e) {
                e.preventDefault();
                advance();
            });
        }
        if (wrap) {
            wrap.addEventListener('click', function (e) {
                if (e.target === nextBtn || (nextBtn && nextBtn.contains(e.target))) return;
                advance();
            });
        }

        show(idx);
        cycleMs = pickCycle();
        raf = window.requestAnimationFrame(tick);
    });
})();
