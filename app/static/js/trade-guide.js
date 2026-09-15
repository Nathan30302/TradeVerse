/**
 * Voice Journal — conversation is the interface.
 * Same Trade POST as Log Trade. Structured data is extracted in the background.
 */
(function () {
  'use strict';

  var form = document.getElementById('trade-guide-form');
  if (!form) return;

  var boot = {};
  try {
    var bootEl = document.getElementById('tv-vj-boot');
    boot = bootEl ? JSON.parse(bootEl.textContent || '{}') : {};
  } catch (e) {
    boot = {};
  }

  var stage = document.getElementById('tv-vj-stage');
  var orbBtn = document.getElementById('tv-vj-orb');
  var canvas = document.getElementById('tv-vj-canvas');
  var aiEl = document.getElementById('tv-vj-ai');
  var liveEl = document.getElementById('tv-vj-live');
  var statusEl = document.getElementById('tv-vj-status');
  var errEl = document.getElementById('tv-vj-mic-err');
  var shotEl = document.getElementById('tv-vj-shot');
  var journalEl = document.getElementById('tv-vj-journal');
  var summaryEl = document.getElementById('tv-vj-summary');

  var state = 'idle';
  var draft = {};
  var history = [];
  var transcriptDump = [];
  var hasShot = false;
  var skipShot = false;
  var committing = false;
  var lastReply = '';

  var rec = {
    stream: null,
    sr: null,
    mr: null,
    chunks: [],
    recording: false,
    text: '',
    mime: '',
    silence: null,
    maxTimer: null,
    ctx: null,
    srcNode: null,
    analyser: null,
    loudWatch: null,
    gen: 0,
    raf: 0,
    amp: 0,
    freq: null
  };

  function csrf() {
    if (typeof window.tvGetCsrf === 'function') return window.tvGetCsrf() || '';
    var el = form.querySelector('[name="csrf_token"]');
    return el ? el.value : '';
  }

  function setVal(id, value) {
    var el = document.getElementById(id);
    if (el) el.value = value == null ? '' : String(value);
  }

  function val(id) {
    var el = document.getElementById(id);
    return el ? String(el.value || '').trim() : '';
  }

  function setState(next) {
    state = next;
    if (stage) stage.setAttribute('data-state', next);
    if (statusEl) {
      statusEl.textContent =
        next === 'listening' ? 'Listening' :
        next === 'thinking' ? 'Thinking' :
        next === 'speaking' ? 'Speaking' :
        next === 'review' ? 'Ready to save' :
        'Tap when you’re ready';
    }
  }

  function showErr(msg) {
    if (!errEl) return;
    if (!msg) {
      errEl.classList.add('d-none');
      errEl.textContent = '';
      return;
    }
    errEl.textContent = msg;
    errEl.classList.remove('d-none');
  }

  function setAi(text) {
    lastReply = String(text || '');
    if (aiEl) {
      aiEl.textContent = lastReply;
      aiEl.classList.add('is-in');
    }
  }

  function setLive(text) {
    if (!liveEl) return;
    var shown = String(text || '').trim();
    liveEl.textContent = shown;
    liveEl.classList.toggle('is-on', !!shown);
    var wrap = document.getElementById('tv-vj-live-wrap');
    if (wrap) wrap.classList.toggle('is-on', state === 'listening' || !!shown);
  }

  function pickMime() {
    var types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac', 'audio/mpeg'];
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
    for (var i = 0; i < types.length; i++) {
      try { if (MediaRecorder.isTypeSupported(types[i])) return types[i]; } catch (e) {}
    }
    return '';
  }

  function blobName(mime) {
    if ((mime || '').indexOf('mp4') !== -1 || (mime || '').indexOf('aac') !== -1) return 'note.m4a';
    if ((mime || '').indexOf('mpeg') !== -1) return 'note.mp3';
    return 'note.webm';
  }

  function ensureStream() {
    if (rec.stream && rec.stream.active) return Promise.resolve(rec.stream);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.reject(new Error('no-mic'));
    }
    return navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: { ideal: true },
        noiseSuppression: { ideal: true },
        autoGainControl: { ideal: true }
      },
      video: false
    }).then(function (stream) {
      rec.stream = stream;
      return stream;
    });
  }

  function unlockAudio() {
    try {
      if (window.speechSynthesis) {
        window.speechSynthesis.resume();
        var unlock = new SpeechSynthesisUtterance(' ');
        unlock.volume = 0;
        window.speechSynthesis.speak(unlock);
      }
    } catch (e) {}
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        if (!rec.ctx) rec.ctx = new AC();
        rec.ctx.resume();
      }
    } catch (e) {}
  }

  function stopTTS() {
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) {}
    var a = document.getElementById('tv-vj-tts');
    if (a) {
      try { a.pause(); } catch (e) {}
      a.remove();
    }
  }

  function speak(text, then) {
    var line = String(text || '').trim();
    if (!line) {
      setTimeout(function () { if (typeof then === 'function') then(); }, 0);
      return;
    }
    setState('speaking');
    setAi(line);
    stopTTS();
    var wrapped = function () {
      setTimeout(function () { if (typeof then === 'function') then(); }, 520);
    };
    var done = wrapped;

    function browserSpeak() {
      if (!window.speechSynthesis) { done(); return; }
      try {
        var u = new SpeechSynthesisUtterance(line);
        u.rate = 1.04;
        u.pitch = 1;
        u.onend = done;
        u.onerror = done;
        window.speechSynthesis.speak(u);
      } catch (e) {
        done();
      }
    }

    if (!boot.speakUrl) {
      browserSpeak();
      return;
    }
    fetch(boot.speakUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify({ text: line })
    }).then(function (r) {
      if (!r.ok) throw new Error('tts');
      return r.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var audio = document.createElement('audio');
      audio.id = 'tv-vj-tts';
      audio.src = url;
      audio.addEventListener('ended', done, { once: true });
      audio.addEventListener('error', function () { browserSpeak(); }, { once: true });
      document.body.appendChild(audio);
      var play = audio.play();
      if (play && play.catch) play.catch(function () { browserSpeak(); });
    }).catch(function () {
      browserSpeak();
    });
  }

  function attachAnalyser(stream) {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      if (!rec.ctx) rec.ctx = new AC();
      if (rec.ctx.state === 'suspended') rec.ctx.resume();
      if (!rec.srcNode) {
        rec.srcNode = rec.ctx.createMediaStreamSource(stream);
        rec.analyser = rec.ctx.createAnalyser();
        rec.analyser.fftSize = 256;
        rec.analyser.smoothingTimeConstant = 0.72;
        rec.srcNode.connect(rec.analyser);
      }
      rec.freq = new Uint8Array(rec.analyser.frequencyBinCount);
    } catch (e) { /* ignore */ }
  }

  function rgbOf(color, a) {
    var c = String(color || '').trim();
    var hex = c.match(/^#([0-9a-f]{6})$/i);
    if (hex) {
      var n = parseInt(hex[1], 16);
      return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
    }
    var rgb = c.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (rgb) return 'rgba(' + rgb[1] + ',' + rgb[2] + ',' + rgb[3] + ',' + a + ')';
    return 'rgba(20,184,166,' + a + ')';
  }

  function drawOrb() {
    rec.raf = requestAnimationFrame(drawOrb);
    if (!canvas || !canvas.getContext) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var css = 280;
    if (canvas.width !== css * dpr || canvas.height !== css * dpr) {
      canvas.width = css * dpr;
      canvas.height = css * dpr;
    }
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var w = css;
    var h = css;
    var cx = w / 2;
    var cy = h / 2;
    ctx.clearRect(0, 0, w, h);

    var amp = 0.08;
    if (rec.analyser && rec.freq && (state === 'listening' || rec.recording)) {
      rec.analyser.getByteFrequencyData(rec.freq);
      var sum = 0;
      for (var i = 0; i < rec.freq.length; i++) sum += rec.freq[i];
      amp = Math.min(1, (sum / rec.freq.length) / 90);
    } else if (state === 'speaking') {
      amp = 0.34 + Math.sin(Date.now() / 160) * 0.14;
    } else if (state === 'thinking') {
      amp = 0.18 + Math.sin(Date.now() / 380) * 0.08;
    } else {
      amp = 0.12 + Math.sin(Date.now() / 900) * 0.04;
    }
    rec.amp = rec.amp * 0.72 + amp * 0.28;

    var accent = getComputedStyle(document.documentElement).getPropertyValue('--tv-accent-bright').trim() || '#14b8a6';
    var deep = getComputedStyle(document.documentElement).getPropertyValue('--tv-accent').trim() || '#0f766e';

    var glow = ctx.createRadialGradient(cx, cy, 8, cx, cy, 128 + rec.amp * 46);
    glow.addColorStop(0, rgbOf(accent, 0.28 + rec.amp * 0.38));
    glow.addColorStop(0.55, rgbOf(deep, 0.12 + rec.amp * 0.12));
    glow.addColorStop(1, rgbOf(accent, 0));
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);

    var bars = rec.freq && state === 'listening' ? 40 : 28;
    var radius = 64 + rec.amp * 16;
    for (var b = 0; b < bars; b++) {
      var mag = rec.freq && state === 'listening'
        ? rec.freq[Math.floor(b * (rec.freq.length / bars))] / 255
        : 0.22 + Math.sin(Date.now() / 260 + b) * 0.1;
      var len = 10 + mag * (38 + rec.amp * 30);
      var ang = (b / bars) * Math.PI * 2 - Math.PI / 2;
      ctx.beginPath();
      ctx.strokeStyle = b % 2 ? accent : deep;
      ctx.globalAlpha = 0.38 + mag * 0.55;
      ctx.lineWidth = 3.2;
      ctx.lineCap = 'round';
      ctx.moveTo(cx + Math.cos(ang) * radius, cy + Math.sin(ang) * radius);
      ctx.lineTo(cx + Math.cos(ang) * (radius + len), cy + Math.sin(ang) * (radius + len));
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.fillStyle = deep;
    ctx.arc(cx, cy, 40 + rec.amp * 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.fillStyle = accent;
    ctx.arc(cx, cy, 23 + rec.amp * 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.fillStyle = 'rgba(255,255,255,0.22)';
    ctx.arc(cx - 8, cy - 10, 8 + rec.amp * 2, 0, Math.PI * 2);
    ctx.fill();
  }

  function watchLoudness() {
    if (!rec.analyser) return;
    var data = new Uint8Array(rec.analyser.fftSize);
    var quiet = 0;
    var heard = false;
    clearInterval(rec.loudWatch);
    rec.loudWatch = setInterval(function () {
      if (!rec.recording) {
        clearInterval(rec.loudWatch);
        return;
      }
      rec.analyser.getByteTimeDomainData(data);
      var sum = 0;
      for (var i = 0; i < data.length; i++) {
        var v = (data[i] - 128) / 128;
        sum += v * v;
      }
      var rms = Math.sqrt(sum / data.length);
      if (rms > 0.042) {
        heard = true;
        quiet = 0;
      } else {
        quiet += 100;
      }
      if (heard && quiet >= 2400) stopRec(false);
      else if (!heard && quiet >= 10000) stopRec(false);
    }, 100);
  }

  function startSpeech() {
    var Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor) return false;
    try {
      rec.sr = new Ctor();
      rec.sr.continuous = true;
      rec.sr.interimResults = true;
      rec.sr.lang = 'en-US';
      rec.sr.onresult = function (ev) {
        var finalTxt = '';
        var interim = '';
        for (var i = ev.resultIndex; i < ev.results.length; i++) {
          var t = ev.results[i][0].transcript;
          if (ev.results[i].isFinal) finalTxt += t;
          else interim += t;
        }
        if (finalTxt) rec.text = (rec.text + ' ' + finalTxt).trim();
        setLive(rec.text || interim);
        if (rec.text || interim) {
          clearTimeout(rec.silence);
          rec.silence = setTimeout(function () {
            if (rec.recording) stopRec(false);
          }, 2500);
        }
      };
      rec.sr.onerror = function () {};
      rec.sr.start();
      return true;
    } catch (e) {
      return false;
    }
  }

  function startRec() {
    if (rec.recording || committing || state === 'review') return;
    rec.text = '';
    rec.chunks = [];
    rec.gen += 1;
    var gen = rec.gen;
    setLive('');
    showErr('');
    ensureStream().then(function (stream) {
      if (gen !== rec.gen) return;
      attachAnalyser(stream);
      rec.mime = pickMime();
      try {
        rec.mr = rec.mime ? new MediaRecorder(stream, { mimeType: rec.mime }) : new MediaRecorder(stream);
      } catch (e) {
        rec.mr = new MediaRecorder(stream);
      }
      rec.mr.ondataavailable = function (e) {
        if (e.data && e.data.size) rec.chunks.push(e.data);
      };
      try { rec.mr.start(); } catch (e) { rec.mr.start(); }
      startSpeech();
      rec.recording = true;
      setState('listening');
      watchLoudness();
      clearTimeout(rec.maxTimer);
      rec.maxTimer = setTimeout(function () {
        if (rec.recording) stopRec(false);
      }, 25000);
    }).catch(function () {
      showErr(window.isSecureContext
        ? 'Allow the microphone, then tap again.'
        : 'Voice needs HTTPS.');
      setState('idle');
    });
  }

  function stopRec(silent) {
    clearTimeout(rec.silence);
    clearTimeout(rec.maxTimer);
    clearInterval(rec.loudWatch);
    if (!rec.recording && !rec.mr) {
      try { if (rec.sr) rec.sr.stop(); } catch (e) {}
      return;
    }
    rec.recording = false;
    var gen = rec.gen;
    var box = { blob: null, recDone: false, srDone: false, silent: !!silent };

    function go() {
      if (gen !== rec.gen) return;
      if (!box.recDone || !box.srDone) return;
      if (box.silent) return;
      finishUtterance(rec.text, box.blob);
    }

    var sr = rec.sr;
    rec.sr = null;
    if (sr) {
      try { sr.stop(); } catch (e) {}
    }
    setTimeout(function () {
      box.srDone = true;
      go();
    }, silent ? 0 : 300);

    var mr = rec.mr;
    rec.mr = null;
    if (!mr) {
      box.recDone = true;
      go();
      return;
    }
    mr.onstop = function () {
      if (gen !== rec.gen) return;
      box.blob = rec.chunks.length ? new Blob(rec.chunks, { type: rec.mime || mr.mimeType || 'audio/webm' }) : null;
      rec.chunks = [];
      box.recDone = true;
      go();
    };
    try {
      if (typeof mr.requestData === 'function' && mr.state === 'recording') mr.requestData();
    } catch (e) {}
    try {
      if (mr.state !== 'inactive') mr.stop();
      else {
        box.recDone = true;
        go();
      }
    } catch (e) {
      box.recDone = true;
      go();
    }
  }

  function tokensOf(text) {
    return String(text || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/).filter(Boolean);
  }

  function tokenOverlap(a, b) {
    var at = tokensOf(a);
    var bt = tokensOf(b);
    if (!at.length || !bt.length) return 0;
    var set = {};
    bt.forEach(function (w) { set[w] = true; });
    var hit = 0;
    at.forEach(function (w) { if (set[w]) hit += 1; });
    return hit / Math.min(at.length, bt.length);
  }

  function looksLikeEcho(text) {
    var q = tokensOf(lastReply).join(' ');
    var a = tokensOf(text).join(' ');
    if (!a || !q || a.length < 8) return false;
    if (a === q || a.indexOf(q) !== -1) return true;
    if (q.indexOf(a) !== -1 && a.length >= 12) return true;
    var at = tokensOf(text);
    var qt = tokensOf(lastReply);
    if (at.length < 3) return false;
    var hit = 0;
    var qset = {};
    qt.forEach(function (w) { qset[w] = true; });
    at.forEach(function (w) { if (qset[w]) hit += 1; });
    return (hit / at.length) >= 0.78 && at.length <= qt.length + 4;
  }

  function isPromptLeak(text) {
    var t = String(text || '').toLowerCase();
    return t.indexOf('trading journal') !== -1 || t.indexOf('symbols: eurusd') !== -1;
  }

  function pickTranscript(whisper, local) {
    whisper = String(whisper || '').trim();
    local = String(local || '').trim();
    if (isPromptLeak(whisper)) whisper = '';
    if (looksLikeEcho(whisper)) whisper = '';
    if (looksLikeEcho(local)) local = '';
    if (whisper && !local) return whisper;
    if (local && !whisper) return local;
    if (!whisper && !local) return '';
    var ov = tokenOverlap(whisper, local);
    if (ov >= 0.4) return whisper;
    if (ov < 0.28) return local;
    return whisper;
  }

  function finishUtterance(srText, blob) {
    var local = String(srText || '').trim();
    if (looksLikeEcho(local)) local = '';
    var blobOk = !!(blob && blob.size > 1200 && boot.transcribeEnabled);
    if (!blobOk) {
      if (local) sendTurn(local);
      else {
        setLive('');
        startRec();
      }
      return;
    }
    committing = true;
    setState('thinking');
    setLive(local || '…');
    var fd = new FormData();
    fd.append('audio', blob, blobName(blob.type || rec.mime));
    fetch(boot.transcribeUrl || '/api/voice/transcribe', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf() },
      body: fd
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        committing = false;
        var whispered = res && res.ok && res.d && res.d.text ? String(res.d.text).trim() : '';
        var text = pickTranscript(whispered, local);
        if (text) sendTurn(text);
        else startRec();
      })
      .catch(function () {
        committing = false;
        if (local) sendTurn(local);
        else startRec();
      });
  }

  function applyForm(fields, instrument) {
    if (!fields) return;
    Object.keys(fields).forEach(function (k) {
      if (k === 'from_guide' || k === 'from_voice' || k === 'guide_voice_dump') return;
      if (document.getElementById(k)) setVal(k, fields[k]);
    });
    if (instrument && instrument.id) {
      setVal('instrument_id', instrument.id);
      setVal('symbol', instrument.symbol);
      draft.instrument_id = instrument.id;
      draft.symbol = instrument.symbol;
    }
  }

  function renderJournal(data) {
    if (!summaryEl) return;
    var d = (data && data.draft) || draft;
    var m = (data && data.metrics) || {};
    var side = d.trade_type === 'SELL' ? 'Short' : 'Long';
    var status = d.status === 'closed' ? 'Closed' : 'Open';
    var rows = [
      [side + ' ' + (d.symbol || ''), status],
      ['In', d.entry_price != null ? d.entry_price : '—'],
      ['Stop', d.stop_loss != null ? d.stop_loss : '—'],
      ['Target', d.take_profit != null ? d.take_profit : '—']
    ];
    if (d.status === 'closed') rows.push(['Out', d.exit_price != null ? d.exit_price : '—']);
    if (m.rr_label) rows.push(['R:R', m.rr_label]);
    if (d.session_type) rows.push(['Session', d.session_type]);
    if (d.setup_tags && d.setup_tags.length) rows.push(['Setup', d.setup_tags.join(', ')]);
    if (d.thesis_notes) rows.push(['Thesis', d.thesis_notes]);
    var html = '<article class="tv-vj-card">';
    rows.forEach(function (row, i) {
      if (i === 0) html += '<h2>' + esc(row[0]) + ' <span>' + esc(row[1]) + '</span></h2>';
      else html += '<div class="tv-vj-row"><span>' + esc(row[0]) + '</span><strong>' + esc(row[1]) + '</strong></div>';
    });
    html += '</article>';
    summaryEl.innerHTML = html;
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c];
    });
  }

  function sendTurn(text) {
    committing = true;
    setState('thinking');
    setLive(text);
    transcriptDump.push(text);
    history.push({ role: 'user', content: text });
    setVal('guide_voice_dump', transcriptDump.join('\n'));
    fetch(boot.turnUrl || '/trade/api/voice-turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), 'X-CSRF-Token': csrf() },
      body: JSON.stringify({
        transcript: text,
        draft: draft,
        history: history,
        has_screenshot: hasShot,
        skip_screenshot: skipShot
      })
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        committing = false;
        if (!data || !data.ok) {
          setAi('Say that once more?');
          speak('Say that once more?', startRec);
          return;
        }
        draft = data.draft || draft;
        applyForm(data.form, data.instrument);
        setVal('guide_voice_dump', transcriptDump.join('\n'));
        history.push({ role: 'assistant', content: data.reply || '' });
        if (data.ask_screenshot && shotEl) shotEl.classList.remove('d-none');
        if (data.complete && !data.ask_screenshot) {
          if (!(data.instrument && data.instrument.id) && !val('instrument_id')) {
            speak('I didn’t catch the market — say the ticker once more?', startRec);
            return;
          }
          enterReview(data);
          return;
        }
        speak(data.reply, function () {
          if (state === 'review') return;
          startRec();
        });
      })
      .catch(function () {
        committing = false;
        speak('I missed that — try once more.', startRec);
      });
  }

  function enterReview(data) {
    stopRec(true);
    stopTTS();
    setState('review');
    setLive('');
    if (shotEl && hasShot) shotEl.classList.add('d-none');
    if (journalEl) journalEl.classList.remove('d-none');
    setVal('guide_voice_dump', transcriptDump.join('\n'));
    renderJournal(data);
    speak(data && data.reply ? data.reply : 'Got it — that’s everything I need.');
  }

  function begin() {
    if (state !== 'idle' && state !== 'review') return;
    if (journalEl) journalEl.classList.add('d-none');
    unlockAudio();
    var opening = boot.mode === 'quick'
      ? 'Give me the short version — pair, side, levels.'
      : (boot.complete && boot.complete.symbol
        ? ('Let’s finish the notes on ' + boot.complete.symbol + '.')
        : 'Hey — tell me about the trade.');
    ensureStream().then(function (stream) {
      attachAnalyser(stream);
      if (!rec.raf) drawOrb();
      speak(opening, startRec);
    }).catch(function () {
      showErr(window.isSecureContext
        ? 'Allow the microphone, then tap again.'
        : 'Voice needs HTTPS.');
    });
  }

  if (orbBtn) {
    orbBtn.addEventListener('click', function () {
      if (state === 'idle' || state === 'review') begin();
      else if (state === 'listening') stopRec(false);
      else if (state === 'speaking') {
        stopTTS();
        setTimeout(startRec, 220);
      }
    });
  }

  document.getElementById('tv-vj-shot-pick') && document.getElementById('tv-vj-shot-pick').addEventListener('click', function () {
    var input = document.getElementById('before_screenshot');
    if (input) input.click();
  });
  document.getElementById('tv-vj-shot-skip') && document.getElementById('tv-vj-shot-skip').addEventListener('click', function () {
    skipShot = true;
    if (shotEl) shotEl.classList.add('d-none');
    sendTurn('no screenshot');
  });

  var beforeInput = document.getElementById('before_screenshot');
  if (beforeInput) {
    beforeInput.addEventListener('change', function () {
      var file = beforeInput.files && beforeInput.files[0];
      if (!file) return;
      hasShot = true;
      var url = URL.createObjectURL(file);
      var previews = document.getElementById('tv-vj-shot-previews');
      if (previews) {
        previews.innerHTML = '<img src="' + url + '" alt="Chart">';
      }
      if (boot.extractUrl) {
        var fd = new FormData();
        fd.append('image', file, file.name || 'chart.jpg');
        fetch(boot.extractUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrf() },
          body: fd
        }).then(function (r) { return r.json(); }).then(function (data) {
          var fields = (data && data.fields) || {};
          draft = Object.assign({}, draft, fields);
          if (data && data.instrument) {
            draft.instrument_id = data.instrument.id;
            draft.symbol = data.instrument.symbol;
          }
          sendTurn('I uploaded the chart.');
        }).catch(function () {
          sendTurn('I uploaded the chart.');
        });
      } else {
        sendTurn('I uploaded the chart.');
      }
    });
  }

  document.getElementById('tv-vj-fix') && document.getElementById('tv-vj-fix').addEventListener('click', function () {
    if (journalEl) journalEl.classList.add('d-none');
    skipShot = true;
    speak('What should I change?', startRec);
  });

  form.addEventListener('submit', function () {
    if (!val('lot_size')) setVal('lot_size', '1');
    var why = val('guide_why') || val('guide_voice_dump');
    if (why && !val('pre_trade_plan')) setVal('pre_trade_plan', why);
    var post = val('guide_voice_dump') || why;
    if (post && !val('post_trade_notes')) setVal('post_trade_notes', post);
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
    stopTTS();
  });

  if (!rec.raf) drawOrb();

  window.addEventListener('pagehide', function () {
    stopTTS();
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
    cancelAnimationFrame(rec.raf);
  });
})();
