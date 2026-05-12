/**
 * Browser speech-to-text for trade note fields (Web Speech API).
 * Small mic control sits inside the textarea corner (not a large toolbar above).
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
    this.shell = null;
    this.statusText = null;
    this.interimEl = null;
    this.btnToggle = null;
  }

  VoiceField.prototype.mount = function () {
    this.ta = document.getElementById(this.textareaId);
    if (!this.ta || !this.ta.parentNode) return;

    const shell = document.createElement('div');
    shell.className = 'tv-voice-field-shell position-relative';
    const parent = this.ta.parentNode;
    parent.insertBefore(shell, this.ta);
    shell.appendChild(this.ta);

    const dock = document.createElement('div');
    dock.className = 'tv-voice-dock';
    shell.appendChild(dock);

    this.shell = shell;

    if (!SR) {
      const warn = document.createElement('span');
      warn.className = 'small text-muted';
      warn.textContent = 'Voice needs Chrome, Edge, or Safari (HTTPS).';
      dock.appendChild(warn);
      return;
    }

    this.btnToggle = document.createElement('button');
    this.btnToggle.type = 'button';
    this.btnToggle.className = 'btn btn-link p-1 tv-voice-fab';
    this.btnToggle.setAttribute('aria-pressed', 'false');
    this.btnToggle.setAttribute('title', 'Speak to type');
    this.btnToggle.setAttribute('aria-label', 'Start voice dictation');
    this.btnToggle.innerHTML =
      '<i class="fas fa-microphone tv-voice-fab-icon" aria-hidden="true"></i>';
    dock.appendChild(this.btnToggle);

    const statusRow = document.createElement('div');
    statusRow.className = 'tv-voice-status-row small mt-1 px-1';
    shell.appendChild(statusRow);

    this.statusText = document.createElement('span');
    this.statusText.className = 'text-muted tv-voice-status-text';
    statusRow.appendChild(this.statusText);

    this.interimEl = document.createElement('span');
    this.interimEl.className = 'text-info fst-italic ms-1 tv-voice-interim';
    this.interimEl.setAttribute('aria-live', 'polite');
    statusRow.appendChild(this.interimEl);

    const self = this;
    this.btnToggle.addEventListener('click', function () {
      if (self.active) self.stop();
      else self.start();
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
      if (this.statusText) this.statusText.textContent = 'Could not start microphone.';
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
      if (self.shell) self.shell.classList.add('tv-voice-recording');
      if (self.btnToggle) {
        self.btnToggle.setAttribute('aria-pressed', 'true');
        self.btnToggle.setAttribute('aria-label', 'Stop voice dictation');
        self.btnToggle.innerHTML =
          '<i class="fas fa-stop tv-voice-fab-icon tv-voice-fab-icon--on" aria-hidden="true"></i>';
      }
      if (self.statusText) self.statusText.textContent = 'Listening… speak naturally.';
      if (self.interimEl) self.interimEl.textContent = '';
    };

    this.rec.onerror = function (ev) {
      const code = ev && ev.error ? String(ev.error) : '';
      const friendly = {
        'not-allowed': 'Mic blocked — allow in the browser bar.',
        'service-not-allowed': 'Speech recognition disabled.',
        'audio-capture': 'No microphone found.',
        'network': 'Network error — try again.',
        'aborted': '',
        'no-speech': 'No speech heard — tap again when ready.',
      };
      if (self.interimEl) self.interimEl.textContent = '';
      self.rec = null;
      self.cleanupUi();
      if (code === 'aborted') return;
      const msg = friendly[code] || (code ? 'Voice: ' + code : 'Mic error');
      if (msg && self.statusText) {
        self.statusText.textContent = msg;
        if (code === 'no-speech') {
          setTimeout(function () {
            if (self.statusText) self.statusText.textContent = '';
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
          if (self.interimEl) self.interimEl.textContent = '';
        } else {
          interim += text;
        }
      }
      if (self.interimEl) self.interimEl.textContent = interim;
    };

    try {
      this.rec.start();
    } catch (e) {
      if (self.statusText) self.statusText.textContent = 'Tap again to start.';
      self.cleanupUi();
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
    if (this.shell) this.shell.classList.remove('tv-voice-recording');
    if (this.btnToggle) {
      this.btnToggle.setAttribute('aria-pressed', 'false');
      this.btnToggle.setAttribute('aria-label', 'Start voice dictation');
      this.btnToggle.innerHTML =
        '<i class="fas fa-microphone tv-voice-fab-icon" aria-hidden="true"></i>';
    }
    if (this.statusText) this.statusText.textContent = '';
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
