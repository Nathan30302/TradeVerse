/**
 * Trade note voice input: Web Speech API where available; MediaRecorder + server
 * Whisper fallback for in-app browsers (Instagram, Facebook, etc.).
 */
(function (global) {
  'use strict';

  const SpeechRecognitionCtor =
    global.SpeechRecognition || global.webkitSpeechRecognition;

  const TRANSCRIBE_URL =
    (global.TV_VOICE && global.TV_VOICE.transcribeUrl) ||
    '/api/voice/transcribe';
  const TRANSCRIBE_ENABLED =
    global.TV_VOICE && global.TV_VOICE.transcribeEnabled === true;

  function getCsrf() {
    if (typeof global.tvGetCsrf === 'function') {
      return global.tvGetCsrf() || '';
    }
    const el = document.querySelector('[name="csrf_token"]');
    return el ? el.value : '';
  }

  function detectEnv() {
    const ua = navigator.userAgent || '';
    const inApp = /Instagram|FBAN|FBAV|FB_IAB|Line\/|Twitter|Snapchat|TikTok|LinkedInApp|MicroMessenger/i.test(
      ua
    );
    const secure = !!global.isSecureContext;
    const hasSR = !!SpeechRecognitionCtor;
    const hasMR =
      typeof global.MediaRecorder !== 'undefined' &&
      !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    let mode = 'unsupported';
    if (secure && hasSR) mode = 'speech';
    else if (secure && hasMR && TRANSCRIBE_ENABLED) mode = 'record';
    else if (secure && hasMR) mode = 'record-unconfigured';
    return { inApp, secure, hasSR, hasMR, mode };
  }

  function insertAtCursor(textarea, text) {
    if (!textarea || text == null) return;
    const chunk = String(text).trim();
    if (!chunk) return;
    const start =
      textarea.selectionStart != null ? textarea.selectionStart : textarea.value.length;
    const end = textarea.selectionEnd != null ? textarea.selectionEnd : textarea.value.length;
    const before = textarea.value.slice(0, start);
    const after = textarea.value.slice(end);
    const needsSpace = before.length > 0 && !/\s$/.test(before) && !/^[,;.!?]/.test(chunk);
    const insert = (needsSpace ? ' ' : '') + chunk;
    textarea.value = before + insert + after;
    const pos = before.length + insert.length;
    try {
      textarea.selectionStart = textarea.selectionEnd = pos;
    } catch (e) {
      /* ignore */
    }
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function setGlobalRecording(on) {
    global.__tvVoiceRecordingCount = Math.max(
      0,
      (global.__tvVoiceRecordingCount || 0) + (on ? 1 : -1)
    );
    global.tvVoiceRecordingActive = global.__tvVoiceRecordingCount > 0;
  }

  function requestMicAccess() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.reject(new Error('no-getusermedia'));
    }
    return navigator.mediaDevices
      .getUserMedia({ audio: true, video: false })
      .then(function (stream) {
        stream.getTracks().forEach(function (t) {
          try {
            t.stop();
          } catch (e) {
            /* ignore */
          }
        });
        return true;
      });
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
    this.env = detectEnv();
    this.mediaRecorder = null;
    this.mediaStream = null;
    this.recordChunks = [];
    this.mode = this.env.mode;
  }

  VoiceField.prototype.unsupportedMessage = function () {
    const e = this.env;
    if (!e.secure) {
      return 'Voice needs a secure connection (HTTPS).';
    }
    if (e.inApp) {
      return 'In-app browsers (Instagram, etc.) often block voice. Open this page in Safari or Chrome, then try again.';
    }
    if (e.mode === 'record-unconfigured') {
      return 'Live dictation needs Chrome, Edge, or Safari. Server transcription is not configured.';
    }
    return 'Voice typing is not supported in this browser. Use Safari or Chrome.';
  };

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

    if (this.mode === 'unsupported') {
      const warn = document.createElement('span');
      warn.className = 'small text-muted';
      warn.textContent = this.unsupportedMessage();
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

  VoiceField.prototype.setRecordingUi = function (on) {
    if (on) {
      if (this.shell) this.shell.classList.add('tv-voice-recording');
      if (this.btnToggle) {
        this.btnToggle.setAttribute('aria-pressed', 'true');
        this.btnToggle.setAttribute('aria-label', 'Stop voice dictation');
        this.btnToggle.innerHTML =
          '<i class="fas fa-stop tv-voice-fab-icon tv-voice-fab-icon--on" aria-hidden="true"></i>';
      }
    } else {
      if (this.shell) this.shell.classList.remove('tv-voice-recording');
      if (this.btnToggle) {
        this.btnToggle.setAttribute('aria-pressed', 'false');
        this.btnToggle.setAttribute('aria-label', 'Start voice dictation');
        this.btnToggle.innerHTML =
          '<i class="fas fa-microphone tv-voice-fab-icon" aria-hidden="true"></i>';
      }
    }
  };

  VoiceField.prototype.start = function () {
    if (this.active || !this.ta) return;
    if (this.mode === 'speech') {
      this.startSpeech();
    } else if (this.mode === 'record') {
      this.startRecord();
    }
  };

  VoiceField.prototype.startSpeech = function () {
    const self = this;
    requestMicAccess()
      .catch(function () {
        /* Safari may still allow SpeechRecognition without preflight */
      })
      .finally(function () {
        self._startSpeechRecognition();
      });
  };

  VoiceField.prototype._startSpeechRecognition = function () {
    if (!SpeechRecognitionCtor || this.active) return;
    try {
      this.rec = new SpeechRecognitionCtor();
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
      self.setRecordingUi(true);
      if (self.statusText) self.statusText.textContent = 'Listening… speak naturally.';
      if (self.interimEl) self.interimEl.textContent = '';
    };

    this.rec.onerror = function (ev) {
      const code = ev && ev.error ? String(ev.error) : '';
      const friendly = {
        'not-allowed': 'Mic blocked — allow microphone for this site in browser settings.',
        'service-not-allowed': 'Speech blocked — check Settings → Safari → Microphone.',
        'audio-capture': 'No microphone found.',
        network: 'Network error — try again.',
        aborted: '',
        'no-speech': 'No speech heard — tap again when ready.',
      };
      if (self.interimEl) self.interimEl.textContent = '';
      self.rec = null;
      self.cleanupUi();
      if (code === 'aborted') return;
      let msg = friendly[code] || (code ? 'Voice: ' + code : 'Mic error');
      if (code === 'not-allowed' && self.env.inApp) {
        msg =
          'Mic blocked in this app. Open TradeVerse in Safari or Chrome to use voice notes.';
      }
      if (msg && self.statusText) {
        self.statusText.textContent = msg;
        if (code === 'no-speech') {
          setTimeout(function () {
            if (self.statusText) self.statusText.textContent = '';
          }, 4500);
        }
      }
      if (
        (code === 'service-not-allowed' || code === 'not-allowed') &&
        self.env.hasMR &&
        TRANSCRIBE_ENABLED &&
        self.mode === 'speech'
      ) {
        self.mode = 'record';
        if (self.statusText) {
          self.statusText.textContent += ' Tap mic again to record instead.';
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
        const text = res[0] && res[0].transcript ? res[0].transcript : '';
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
      if (this.statusText) this.statusText.textContent = 'Tap again to start.';
      this.cleanupUi();
    }
  };

  VoiceField.prototype.startRecord = function () {
    const self = this;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (this.statusText) this.statusText.textContent = this.unsupportedMessage();
      return;
    }

    navigator.mediaDevices
      .getUserMedia({ audio: true, video: false })
      .then(function (stream) {
        self.mediaStream = stream;
        self.recordChunks = [];
        const mimeCandidates = [
          'audio/webm;codecs=opus',
          'audio/webm',
          'audio/mp4',
          'audio/aac',
        ];
        let mime = '';
        for (let i = 0; i < mimeCandidates.length; i++) {
          if (global.MediaRecorder.isTypeSupported(mimeCandidates[i])) {
            mime = mimeCandidates[i];
            break;
          }
        }
        try {
          self.mediaRecorder = mime
            ? new global.MediaRecorder(stream, { mimeType: mime })
            : new global.MediaRecorder(stream);
        } catch (err) {
          self.releaseStream();
          if (self.statusText) self.statusText.textContent = 'Could not start recording.';
          return;
        }

        self.mediaRecorder.ondataavailable = function (ev) {
          if (ev.data && ev.data.size > 0) self.recordChunks.push(ev.data);
        };

        self.mediaRecorder.onstop = function () {
          self.uploadRecording();
        };

        self.mediaRecorder.onerror = function () {
          if (self.statusText) self.statusText.textContent = 'Recording error — try again.';
          self.cleanupUi();
        };

        self.mediaRecorder.start(250);
        self.active = true;
        setGlobalRecording(true);
        self.setRecordingUi(true);
        if (self.statusText) {
          self.statusText.textContent = 'Recording… tap stop when finished.';
        }
      })
      .catch(function () {
        let msg = 'Mic blocked — allow microphone for this site.';
        if (self.env.inApp) {
          msg =
            'Mic blocked in this app. Open TradeVerse in Safari or Chrome to use voice notes.';
        }
        if (self.statusText) self.statusText.textContent = msg;
        self.cleanupUi();
      });
  };

  VoiceField.prototype.releaseStream = function () {
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(function (t) {
        try {
          t.stop();
        } catch (e) {
          /* ignore */
        }
      });
    }
    this.mediaStream = null;
  };

  VoiceField.prototype.uploadRecording = function () {
    const self = this;
    const chunks = self.recordChunks || [];
    self.recordChunks = [];
    self.releaseStream();

    if (!chunks.length) {
      if (self.statusText) self.statusText.textContent = 'No audio captured.';
      return;
    }

    const blob = new Blob(chunks, { type: chunks[0].type || 'audio/webm' });
    if (blob.size < 400) {
      if (self.statusText) self.statusText.textContent = 'Recording too short — try again.';
      return;
    }

    if (self.statusText) self.statusText.textContent = 'Transcribing…';

    const fd = new FormData();
    const ext = (blob.type || '').indexOf('mp4') >= 0 ? 'm4a' : 'webm';
    fd.append('audio', blob, 'note.' + ext);

    const csrf = getCsrf();
    fetch(TRANSCRIBE_URL, {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
      headers: {
        'X-CSRFToken': csrf,
        'X-CSRF-Token': csrf,
      },
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          return { ok: resp.ok, status: resp.status, data: data };
        });
      })
      .then(function (result) {
        if (result.ok && result.data && result.data.text) {
          insertAtCursor(self.ta, result.data.text);
          if (self.statusText) self.statusText.textContent = 'Added to your note.';
          setTimeout(function () {
            if (self.statusText) self.statusText.textContent = '';
          }, 2500);
          return;
        }
        const err =
          (result.data && result.data.error) ||
          'Transcription failed. Try again or type your note.';
        if (self.statusText) self.statusText.textContent = err;
      })
      .catch(function () {
        if (self.statusText) {
          self.statusText.textContent = 'Network error — check connection and try again.';
        }
      });
  };

  VoiceField.prototype.stop = function () {
    if (this.mode === 'record' && this.mediaRecorder && this.active) {
      try {
        if (this.mediaRecorder.state !== 'inactive') {
          this.mediaRecorder.stop();
        }
      } catch (e) {
        this.uploadRecording();
      }
      this.mediaRecorder = null;
      this.cleanupUi({ keepStatus: true, keepStream: true });
      return;
    }

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

  VoiceField.prototype.cleanupUi = function (opts) {
    opts = opts || {};
    if (this.active) setGlobalRecording(false);
    this.active = false;
    this.setRecordingUi(false);
    if (!opts.keepStatus && this.statusText) this.statusText.textContent = '';
    if (this.interimEl) this.interimEl.textContent = '';
    if (!opts.keepStream) this.releaseStream();
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
