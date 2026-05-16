/**
 * Auto-rotating motivational quote widget with visible progress timer.
 */
(function (global) {
  'use strict';

  var DEFAULT_INTERVAL_MS = 25000;
  var FADE_MS = 520;

  function shuffle(arr) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i];
      a[i] = a[j];
      a[j] = t;
    }
    return a;
  }

  function normalizeQuote(raw) {
    if (!raw) return null;
    if (typeof raw === 'string') {
      return { text: raw, author: 'TradeVerse', category: '' };
    }
    if (typeof raw === 'object' && raw.text) {
      return {
        text: String(raw.text),
        author: raw.author ? String(raw.author) : 'TradeVerse',
        category: raw.category ? String(raw.category) : '',
      };
    }
    return null;
  }

  function MotivationalQuotes(root) {
    this.root = root;
    this.intervalMs = DEFAULT_INTERVAL_MS;
    this.quotes = [];
    this.order = [];
    this.orderPos = 0;
    this.rafId = null;
    this.cycleStart = 0;
    this.reducedMotion = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;

    this.textWrap = root.querySelector('.tv-quote-text-wrap');
    this.textEl = root.querySelector('.tv-quote-text');
    this.fillEl = root.querySelector('.tv-quote-timer-fill');

    this._loadConfig();
    if (this.quotes.length) {
      var hasContent = this.textEl && this.textEl.textContent.trim().length > 0;
      if (!hasContent) {
        this._showQuote(this.quotes[this.order[0]], false);
      }
      this._startCycle();
    }
  }

  MotivationalQuotes.prototype._loadConfig = function () {
    var raw = this.root.getAttribute('data-quotes');
    var interval = parseInt(this.root.getAttribute('data-interval') || '', 10);
    if (interval >= 15000 && interval <= 60000) {
      this.intervalMs = interval;
    }
    try {
      var parsed = raw ? JSON.parse(raw) : [];
      if (Array.isArray(parsed)) {
        for (var i = 0; i < parsed.length; i++) {
          var q = normalizeQuote(parsed[i]);
          if (q) this.quotes.push(q);
        }
      }
    } catch (e) {
      this.quotes = [];
    }
    this.order = shuffle(this.quotes.map(function (_, idx) { return idx; }));
    this.orderPos = 0;
  };

  MotivationalQuotes.prototype._showQuote = function (quote, animate) {
    if (!quote || !this.textEl) return;
    var self = this;
    var apply = function () {
      self.textEl.textContent = '\u201c' + quote.text + '\u201d';
      if (self.textWrap) {
        self.textWrap.classList.remove('is-fading');
      }
    };
    if (!animate || !this.textWrap || this.reducedMotion) {
      apply();
      return;
    }
    this.textWrap.classList.add('is-fading');
    global.setTimeout(apply, FADE_MS);
  };

  MotivationalQuotes.prototype._nextIndex = function () {
    if (!this.order.length) return 0;
    this.orderPos = (this.orderPos + 1) % this.order.length;
    if (this.orderPos === 0 && this.quotes.length > 1) {
      this.order = shuffle(this.quotes.map(function (_, idx) { return idx; }));
    }
    return this.order[this.orderPos];
  };

  MotivationalQuotes.prototype.advance = function () {
    var self = this;
    if (!this.quotes.length) return;
    if (this.rafId) {
      global.cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    var idx = this._nextIndex();
    this._showQuote(this.quotes[idx], true);
    this._resetProgress();
    this._startCycle();
  };

  MotivationalQuotes.prototype._resetProgress = function () {
    this.cycleStart = 0;
    if (this.fillEl) {
      this.fillEl.style.transform = 'scaleX(0)';
    }
  };

  MotivationalQuotes.prototype._startCycle = function () {
    var self = this;
    if (this.rafId) {
      global.cancelAnimationFrame(this.rafId);
    }
    function tick(ts) {
      if (!self.cycleStart) self.cycleStart = ts;
      var elapsed = ts - self.cycleStart;
      var p = Math.min(elapsed / self.intervalMs, 1);
      if (self.fillEl) {
        self.fillEl.style.transform = 'scaleX(' + p.toFixed(4) + ')';
      }
      if (p >= 1) {
        self.advance();
        return;
      }
      self.rafId = global.requestAnimationFrame(tick);
    }
    this.rafId = global.requestAnimationFrame(tick);
  };

  MotivationalQuotes.prototype.destroy = function () {
    if (this.rafId) {
      global.cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  };

  function initAll() {
    var nodes = document.querySelectorAll('[data-tv-motivational-quotes]');
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i]._tvQuoteInstance) continue;
      nodes[i]._tvQuoteInstance = new MotivationalQuotes(nodes[i]);
    }
  }

  global.TradeVerseMotivationalQuotes = {
    init: initAll,
    MotivationalQuotes: MotivationalQuotes,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})(typeof window !== 'undefined' ? window : this);
