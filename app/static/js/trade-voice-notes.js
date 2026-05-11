/**
 * Browser speech-to-text for trade note fields (Web Speech API).
 * Appends recognized text at the caret; user can edit freely before save.
 */
(function (global) {
  'use strict';

  const SR = global.SpeechRecognition || global.webkitSpeechRecognition;

  function insertAtCursor(textarea, text) {
    if (!textarea || text == null) return;
    const chunk = String(text).trim();
    if (!chunk) return;
    const start = textarea.selectionStart != null ? textarea.selectionStart : textarea.value.length;
    const end = textarea.selectionEnd != null ? textarea.selectionEnd : textarea.value.length;
    const before = textarea.value.slice(0, start);
    const after = textarea.value.slice(end);
    const needsSpace = before.length > 0 && !/\s$/.test(before) && !/^[,;.!?]/.test(chunk);
    const insert = (needsSpace ? ' ' : '') + chunk;
    textarea.value = before + insert + after;
    const pos = before.length + insert.length;
    try {
      textarea.selectionStart = textarea.selectionEnd = pos;
    } catch (e) { /* ignore */ }
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function setGlobalRecording(on) {
    global.__tvVoiceRecordingCount = Math.max(0, (global.__tvVoiceRecordingCount || 0) + (on ? 1 : -1));
    global.tvVoiceRecordingActive = global.__tvVoiceRecordingCount > 0;
  }

  function VoiceField(textareaId) {
    this.textareaId = textareaId;
    this.ta = null;
    this.rec = null;
    this.active = false;
    this.toolbar = null;
    this.statusEl = null;
    this.interimEl = null;
    this.btnStart = null;
    this.btnStop = null;
  }

  VoiceField.prototype.mount = function () {
    this.ta = document.getElementById(this.textareaId);
    if (!this.ta || !this.ta.parentNode) return;

    const wrap = document.createElement('div');
    wrap.className = 'tv-voice-wrap mb-2';

    this.toolbar = document.createElement('div');
    this.toolbar.className = 'd-flex flex-wrap align-items-center gap-2';

    if (!SR) {
      const warn = document.createElement('span');
      warn.className = 'small text-muted';
      warn.textContent = 'Voice dictation needs Chrome, Edge, or Safari (HTTPS).';
      this.toolbar.appendChild(warn);
      wrap.appendChild(this.toolbar);
      this.ta.parentNode.insertBefore(wrap, this.ta);
      return;
    }

    this.wrapEl = wrap;

    this.btnStart = document.createElement('button');
    this.btnStart.type = 'button';
    this.btnStart.className = 'btn btn-sm btn-outline-primary tv-voice-start';
    this.btnStart.innerHTML = '<span class="tv-voice-mic-emoji" aria-hidden="true">🎤</span><span class="ms-1">Start recording</span>';
    this.btnStart.setAttribute('aria-pressed', 'false');
    this.btnStart.setAttribute('aria-label', 'Start voice dictation');

    this.btnStop = document.createElement('button');
    this.btnStop.type = 'button';
    this.btnStop.className = 'btn btn-sm btn-outline-danger tv-voice-stop d-none';
    this.btnStop.innerHTML = '<i class="fas fa-stop me-1" aria-hidden="true"></i>Stop recording';
    this.btnStop.setAttribute('aria-label', 'Stop voice dictation');
    this.btnStop.disabled = true;

    this.statusEl = document.createElement('span');
    this.statusEl.className = 'small text-muted tv-voice-status';
    this.statusEl.textContent = '';

    this.interimEl = document.createElement('span');
    this.interimEl.className = 'small text-info tv-voice-interim ms-1 fst-italic';
    this.interimEl.setAttribute('aria-live', 'polite');
    this.interimEl.textContent = '';

    this.toolbar.appendChild(this.btnStart);
    this.toolbar.appendChild(this.btnStop);
    this.toolbar.appendChild(this.statusEl);
    this.toolbar.appendChild(this.interimEl);
    wrap.appendChild(this.toolbar);
    this.ta.parentNode.insertBefore(wrap, this.ta);

    const self = this;
    this.btnStart.addEventListener('click', function () {
      self.start();
    });
    this.btnStop.addEventListener('click', function () {
      self.stop();
    });

    const form = this.ta.closest('form');
    if (form) {
      form.addEventListener('submit', function () {
        self.stop();
      });
    }
  };

  VoiceField.prototype.start = function () {
    if (!SR || this.active || !this.ta) return;
    try {
      this.rec = new SR();
    } catch (e) {
      this.statusEl.textContent = 'Could not start microphone.';
      return;
    }
    this.rec.lang = document.documentElement.lang || 'en-US';
    this.rec.continuous = true;
    this.rec.interimResults = true;
    this.rec.maxAlternatives = 1;

    const self = this;
    this.rec.onstart = function () {
      self.active = true;
      setGlobalRecording(true);
      if (self.wrapEl) self.wrapEl.classList.add('tv-voice-recording');
      self.btnStart.classList.add('active');
      self.btnStart.setAttribute('aria-pressed', 'true');
      self.btnStop.classList.remove('d-none');
      self.btnStop.disabled = false;
      self.statusEl.textContent = 'Listening… speak naturally; pauses are OK.';
      self.interimEl.textContent = '';
    };

    this.rec.onerror = function (ev) {
      const code = ev && ev.error ? String(ev.error) : '';
      const friendly = {
        'not-allowed': 'Microphone blocked — allow access in the browser address bar.',
        'service-not-allowed': 'Speech recognition disabled — check browser permissions.',
        'audio-capture': 'No microphone found or it is in use by another app.',
        'network': 'Network error — try again in a moment.',
        'aborted': '',
        'no-speech': 'No speech heard — tap Start recording when you are ready.',
      };
      self.interimEl.textContent = '';
      self.rec = null;
      self.cleanupUi();
      if (code === 'aborted') return;
      const msg = friendly[code] || (code ? 'Voice: ' + code : 'Mic error');
      if (msg && self.statusEl) {
        self.statusEl.textContent = msg;
        if (code === 'no-speech') {
          setTimeout(function () {
            if (self.statusEl) self.statusEl.textContent = '';
          }, 4500);
        }
      }
    };

    this.rec.onend = function () {
      self.rec = null;
      self.cleanupUi();
    };

    this.rec.onresult = function (event) {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        const text = (res[0] && res[0].transcript) ? res[0].transcript : '';
        if (res.isFinal) {
          insertAtCursor(self.ta, text);
          self.interimEl.textContent = '';
        } else {
          interim += text;
        }
      }
      if (interim) self.interimEl.textContent = interim;
    };

    try {
      this.rec.start();
    } catch (e) {
      this.statusEl.textContent = 'Tap Start recording again.';
      this.cleanupUi();
    }
  };

  VoiceField.prototype.stop = function () {
    if (!this.rec) {
      this.cleanupUi();
      return;
    }
    try {
      this.rec.stop();
    } catch (e) {
      this.rec = null;
      this.cleanupUi();
    }
  };

  VoiceField.prototype.cleanupUi = function () {
    if (this.active) setGlobalRecording(false);
    this.active = false;
    if (this.wrapEl) this.wrapEl.classList.remove('tv-voice-recording');
    if (this.btnStart) {
      this.btnStart.classList.remove('active');
      this.btnStart.setAttribute('aria-pressed', 'false');
    }
    if (this.btnStop) {
      this.btnStop.classList.add('d-none');
      this.btnStop.disabled = true;
    }
    if (this.statusEl) this.statusEl.textContent = '';
    if (this.interimEl) this.interimEl.textContent = '';
  };

  global.TradeVoiceNotes = {
    mount: function () {
      const ids = Array.prototype.slice.call(arguments);
      ids.forEach(function (id) {
        new VoiceField(id).mount();
      });
    },
  };
})(typeof window !== 'undefined' ? window : this);
