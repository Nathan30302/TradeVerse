/**
 * Voice Journal — one question at a time. Saves through Add Trade (or voice-complete).
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

  var uid = String(boot.userId || (document.body && document.body.getAttribute('data-user-id')) || 'anon');
  var DRAFT_KEY = 'tv_voice_journal_draft_' + uid;
  var HABIT_KEY = 'tv_voice_journal_habits_' + uid;

  var FULL = ['welcome', 'symbol', 'direction', 'status', 'before_shot', 'shot_confirm', 'prices', 'exit', 'session', 'emotions', 'why', 'management', 'after_shot', 'reflection', 'confirm'];
  var QUICK = ['welcome', 'before_shot', 'shot_confirm', 'talk', 'confirm'];

  var mode = boot.mode === 'quick' ? 'quick' : 'full';
  var idx = 0;
  var extracted = {};
  var confirmed = {};
  var beforeUrl = '';
  var afterUrl = '';
  var restoring = false;

  var errEl = document.getElementById('tv-guide-step-err');
  var nextBtn = document.getElementById('tv-guide-next');
  var backBtn = document.getElementById('tv-guide-back');
  var skipBtn = document.getElementById('tv-guide-skip');
  var saveBtn = document.getElementById('tv-guide-save');
  var heading = document.getElementById('tv-vj-heading');
  var promptEl = document.getElementById('tv-vj-prompt');
  var hintEl = document.getElementById('tv-vj-hint');
  var dotsEl = document.getElementById('tv-vj-dots');
  var progressLabel = document.getElementById('tv-vj-progress-label');
  var recorderEl = document.getElementById('tv-vj-recorder');
  var liveEl = document.getElementById('tv-vj-live');

  var COPY = {
    welcome: ['Let’s log your trade.', 'Just talk. I’ll guide you through it.'],
    symbol: ['What did you trade?', 'Say it, or pick from recents.'],
    direction: ['Buy or sell?', 'One tap is enough.'],
    status: ['Still open, or already done?', 'You can close it later if you’re still in it.'],
    before_shot: ['Upload your before-trade screenshot.', 'I’ll try to read the levels so you don’t have to type them.'],
    shot_confirm: ['I found these details.', 'Confirm the important numbers — never saved silently.'],
    prices: ['Entry, stop, and target.', 'Only what’s still missing.'],
    exit: ['Where did you get out?', 'Use the fill, not the price you wished for.'],
    talk: ['Tell me what happened.', '20–60 seconds. I’ll structure it.'],
    session: ['What session were you trading?', 'I can guess from the clock — confirm it.'],
    emotions: ['How were you feeling?', 'Tap a few, or just speak.'],
    why: ['Why did you take this trade?', 'One sentence is enough.'],
    management: ['How did you manage it?', 'Yes / no — skip anything that doesn’t apply.'],
    after_shot: ['After-trade screenshot.', 'Before → after is the journal.'],
    reflection: ['Did you follow your plan?', 'Then one line: what you’d do differently.'],
    confirm: ['Trade ready.', 'Check the numbers, then save.']
  };

  function csrf() {
    if (typeof window.tvGetCsrf === 'function') return window.tvGetCsrf() || '';
    var el = form.querySelector('[name="csrf_token"]');
    return el ? el.value : '';
  }

  function val(id) {
    var el = document.getElementById(id);
    return el ? String(el.value || '').trim() : '';
  }

  function setVal(id, value) {
    var el = document.getElementById(id);
    if (el) el.value = value == null ? '' : value;
  }

  function isClosed() {
    return val('trade_log_status') === 'closed';
  }

  function readHabits() {
    try {
      return JSON.parse(localStorage.getItem(HABIT_KEY) || '{}') || {};
    } catch (e) {
      return {};
    }
  }

  function bumpSkip(step) {
    var h = readHabits();
    h[step] = (h[step] || 0) + 1;
    try { localStorage.setItem(HABIT_KEY, JSON.stringify(h)); } catch (e) {}
  }

  function habitSkip(step) {
    return (readHabits()[step] || 0) >= 3;
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

  function steps() {
    var list = mode === 'quick' ? QUICK.slice() : FULL.slice();
    return list.filter(function (key) {
      if (key === 'welcome' && (boot.complete || boot.mode === 'quick')) return false;
      if (key === 'symbol' && val('instrument_id') && val('symbol') && confirmed.symbol) return false;
      if (key === 'direction' && val('trade_type') && confirmed.side) return false;
      if (key === 'status' && boot.complete) return false;
      if (key === 'shot_confirm' && !extractedHasValues()) return false;
      if (key === 'prices' && val('entry_price') && confirmed.prices) return false;
      if (key === 'exit' && !isClosed()) return false;
      if (key === 'exit' && val('exit_price') && confirmed.exit) return false;
      if (key === 'session' && (val('session_type') || habitSkip('session'))) return false;
      if (key === 'emotions' && habitSkip('emotions')) return false;
      if (key === 'why' && (val('guide_why') || habitSkip('why'))) return false;
      if (key === 'management' && (!isClosed() || habitSkip('management'))) return false;
      if (key === 'after_shot' && !isClosed()) return false;
      if (key === 'reflection' && (!isClosed() || habitSkip('reflection'))) return false;
      return true;
    });
  }

  function extractedHasValues() {
    return !!(extracted.symbol || extracted.trade_type || extracted.entry_price || extracted.stop_loss || extracted.take_profit);
  }

  function optionalStep(key) {
    return ['before_shot', 'after_shot', 'session', 'emotions', 'why', 'management', 'reflection', 'talk'].indexOf(key) !== -1;
  }

  function voiceStep(key) {
    return ['symbol', 'direction', 'prices', 'exit', 'talk', 'emotions', 'why', 'reflection'].indexOf(key) !== -1;
  }

  function currentKey() {
    return steps()[idx] || 'welcome';
  }

  function paint() {
    var list = steps();
    if (idx < 0) idx = 0;
    if (idx >= list.length) idx = list.length - 1;
    var key = list[idx] || 'welcome';
    document.querySelectorAll('.tv-vj-step').forEach(function (el) {
      el.classList.toggle('is-active', el.getAttribute('data-step') === key);
    });
    var copy = COPY[key] || ['Voice Journal', ''];
    if (mode === 'quick' && (key === 'before_shot' || key === 'talk')) {
      copy = ['Have 30 seconds? Let’s log this trade.', copy[1]];
    }
    if (heading) heading.textContent = key === 'welcome' ? 'Let’s log your trade.' : 'Voice Journal';
    if (promptEl) promptEl.textContent = copy[0];
    if (hintEl) hintEl.textContent = copy[1] || '';
    if (dotsEl) {
      dotsEl.textContent = '';
      var shown = list.filter(function (k) { return k !== 'welcome'; });
      var now = shown.indexOf(key);
      shown.forEach(function (k, i) {
        var d = document.createElement('span');
        if (i < now) d.className = 'is-done';
        if (i === now) d.className = 'is-now';
        dotsEl.appendChild(d);
      });
    }
    if (progressLabel) {
      var left = list.length - idx - 1;
      progressLabel.textContent = key === 'confirm' ? 'Ready to save.' : (left <= 2 ? 'Almost there.' : '');
    }
    var last = key === 'confirm';
    if (backBtn) backBtn.disabled = idx === 0;
    if (nextBtn) nextBtn.classList.toggle('d-none', last);
    if (saveBtn) saveBtn.classList.toggle('d-none', !last);
    if (skipBtn) skipBtn.classList.toggle('d-none', last || !optionalStep(key));
    if (recorderEl) recorderEl.classList.toggle('d-none', !voiceStep(key) || key === 'welcome');
    if (last) renderSummary();
    if (key === 'shot_confirm') renderFound();
    if (key === 'session') suggestSessionUI();
    if (key === 'symbol') maybeSymbolConfirm();
    showErr('');
    if (!restoring) saveDraft();
  }

  function go(delta) {
    var key = currentKey();
    if (delta > 0) {
      var msg = validate(key);
      if (msg) {
        showErr(msg);
        return;
      }
      syncVisibleInputs();
    }
    idx += delta;
    paint();
  }

  function validate(key) {
    if (key === 'symbol' && (!val('instrument_id') || !val('symbol'))) {
      return 'Pick a symbol (or say it, then confirm).';
    }
    if (key === 'direction') {
      var d = val('trade_type').toUpperCase();
      if (d !== 'BUY' && d !== 'SELL') return 'Buy or sell?';
    }
    if (key === 'prices' && !val('entry_price')) return 'Entry is required.';
    if (key === 'exit' && isClosed() && !val('exit_price')) return 'Closed trades need an exit price.';
    return '';
  }

  function syncVisibleInputs() {
    var entry = document.getElementById('tv-vj-entry');
    var lot = document.getElementById('tv-vj-lot');
    var sl = document.getElementById('tv-vj-sl');
    var tp = document.getElementById('tv-vj-tp');
    var ex = document.getElementById('tv-vj-exit');
    if (entry && entry.value) setVal('entry_price', entry.value);
    if (lot && lot.value) setVal('lot_size', lot.value);
    if (sl) setVal('stop_loss', sl.value);
    if (tp) setVal('take_profit', tp.value);
    if (ex && ex.value) setVal('exit_price', ex.value);
    var why = document.getElementById('tv-vj-why');
    if (why && why.value.trim()) setVal('guide_why', why.value.trim());
    var refl = document.getElementById('tv-vj-reflect');
    if (refl && refl.value.trim()) setVal('guide_reflection', refl.value.trim());
  }

  function fillPricesFromHidden() {
    var map = { 'tv-vj-entry': 'entry_price', 'tv-vj-lot': 'lot_size', 'tv-vj-sl': 'stop_loss', 'tv-vj-tp': 'take_profit', 'tv-vj-exit': 'exit_price' };
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.value) el.value = val(map[id]);
    });
  }

  function applyInstrument(id, symbol, name) {
    setVal('instrument_id', id);
    setVal('symbol', symbol);
    confirmed.symbol = true;
    if (window.simpleInstrumentPicker && typeof window.simpleInstrumentPicker.selectInstrument === 'function') {
      try { window.simpleInstrumentPicker.selectInstrument(id, symbol, name || symbol); } catch (e) {}
    }
  }

  function applyParsed(parsed, instrument) {
    if (!parsed) return;
    if (instrument && instrument.id) {
      applyInstrument(instrument.id, instrument.symbol, instrument.name);
      confirmed.symbol = !parsed.symbol_needs_confirm;
    } else if (parsed.symbol && val('symbol') !== parsed.symbol) {
      setVal('symbol', parsed.symbol);
      confirmed.symbol = false;
    }
    if (parsed.trade_type) {
      setVal('trade_type', parsed.trade_type);
      confirmed.side = true;
      syncDir();
    }
    ['entry_price', 'stop_loss', 'take_profit', 'exit_price', 'lot_size'].forEach(function (k) {
      if (parsed[k] != null && parsed[k] !== '') {
        setVal(k, parsed[k]);
        if ((parsed.uncertain || []).indexOf(k) !== -1) confirmed.prices = false;
        else if (k === 'entry_price') confirmed.prices = true;
      }
    });
    if (parsed.session_type) {
      setVal('session_type', parsed.session_type);
      setVal('guide_session', parsed.session_type);
    }
    if (parsed.emotions && parsed.emotions.length) {
      setVal('guide_emotions', parsed.emotions.join(', '));
      setVal('guide_feeling_before', parsed.emotions[0]);
      setVal('emotion', parsed.emotions[0]);
      markChips('#tv-vj-emotion-chips [data-emotion]', parsed.emotions);
    }
    if (parsed.setup_tags && parsed.setup_tags.length) {
      setVal('guide_setup_tags', parsed.setup_tags.join(', '));
      markChips('#tv-vj-setup-chips [data-setup]', parsed.setup_tags);
    }
    if (parsed.text && parsed.text.length > 12 && currentKey() !== 'symbol') {
      var dump = val('guide_voice_dump');
      setVal('guide_voice_dump', dump ? dump + ' ' + parsed.text : parsed.text);
    }
    fillPricesFromHidden();
  }

  function markChips(sel, values) {
    var set = {};
    (values || []).forEach(function (v) { set[String(v).toLowerCase()] = true; });
    document.querySelectorAll(sel).forEach(function (btn) {
      var label = (btn.getAttribute('data-emotion') || btn.getAttribute('data-setup') || btn.textContent || '').toLowerCase();
      btn.classList.toggle('is-on', !!set[label]);
    });
  }

  function parseTranscript(text) {
    if (!text || !boot.parseUrl) return Promise.resolve();
    return fetch(boot.parseUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), 'X-CSRF-Token': csrf() },
      body: JSON.stringify({ text: text })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (data && data.parsed) applyParsed(data.parsed, data.instrument);
      if (data && data.parsed && data.parsed.symbol_needs_confirm) {
        confirmed.symbol = false;
      }
      return data;
    }).catch(function () { return null; });
  }

  /* ---------- recorder ---------- */
  var rec = {
    sr: null,
    mr: null,
    stream: null,
    chunks: [],
    paused: false,
    timer: null,
    started: 0,
    elapsed: 0,
    blobUrl: '',
    text: ''
  };

  function fmt(ms) {
    var s = Math.floor(ms / 1000);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  function setLive(on) {
    rec.recording = !!on;
    if (recorderEl) recorderEl.classList.toggle('is-live', !!on);
    var mic = document.getElementById('tv-vj-mic');
    if (mic) mic.classList.toggle('is-live', !!on);
    var icon = document.getElementById('tv-vj-mic-icon');
    if (icon) icon.className = on ? 'fas fa-stop' : 'fas fa-microphone';
    ['tv-vj-pause', 'tv-vj-stop'].forEach(function (id) {
      var b = document.getElementById(id);
      if (b) b.disabled = !on;
    });
  }

  function tick() {
    var el = document.getElementById('tv-vj-timer');
    if (el) el.textContent = fmt(rec.elapsed + (rec.recording && !rec.paused ? Date.now() - rec.started : 0));
  }

  function stopTracks() {
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
    rec.stream = null;
  }

  function finishText(text) {
    rec.text = String(text || '').trim();
    if (liveEl) liveEl.textContent = rec.text ? ('“' + rec.text + '”') : '';
    var box = document.getElementById('tv-vj-rec-confirm');
    if (box) box.classList.toggle('d-none', !rec.text);
    document.getElementById('tv-vj-replay').disabled = !rec.blobUrl;
    document.getElementById('tv-vj-delete-rec').disabled = !rec.text && !rec.blobUrl;
  }

  function startSpeech() {
    var Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor) return false;
    rec.sr = new Ctor();
    rec.sr.continuous = true;
    rec.sr.interimResults = true;
    rec.sr.lang = document.documentElement.lang || 'en-US';
    rec.text = '';
    rec.sr.onresult = function (ev) {
      var finalTxt = '';
      var interim = '';
      for (var i = ev.resultIndex; i < ev.results.length; i++) {
        var t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) finalTxt += t;
        else interim += t;
      }
      if (finalTxt) rec.text = (rec.text + ' ' + finalTxt).trim();
      if (liveEl) liveEl.textContent = rec.text || interim;
    };
    rec.sr.start();
    return true;
  }

  function startMedia() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.reject(new Error('no-mic'));
    }
    return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      rec.stream = stream;
      rec.chunks = [];
      var mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
      rec.mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      rec.mr.ondataavailable = function (e) { if (e.data && e.data.size) rec.chunks.push(e.data); };
      rec.mr.onstop = function () {
        var blob = new Blob(rec.chunks, { type: rec.mr.mimeType || 'audio/webm' });
        if (rec.blobUrl) URL.revokeObjectURL(rec.blobUrl);
        rec.blobUrl = URL.createObjectURL(blob);
        var audio = document.getElementById('tv-vj-audio');
        if (audio) audio.src = rec.blobUrl;
        if (!rec.text && boot.transcribeEnabled) {
          var fd = new FormData();
          fd.append('audio', blob, 'note.webm');
          fetch(boot.transcribeUrl || '/api/voice/transcribe', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf() },
            body: fd
          }).then(function (r) { return r.json(); }).then(function (d) {
            finishText((d && d.text) || rec.text);
          }).catch(function () { finishText(rec.text); });
        } else {
          finishText(rec.text);
        }
      };
      rec.mr.start();
    });
  }

  function startRec() {
    var err = document.getElementById('tv-vj-mic-err');
    if (err) { err.classList.add('d-none'); err.textContent = ''; }
    rec.paused = false;
    rec.started = Date.now();
    rec.elapsed = 0;
    rec.text = '';
    if (liveEl) liveEl.textContent = 'Listening…';
    startSpeech();
    startMedia().then(function () {
      setLive(true);
      rec.timer = setInterval(tick, 250);
    }).catch(function () {
      if (rec.sr) setLive(true);
      else if (err) {
        err.textContent = window.isSecureContext
          ? 'Microphone permission is needed. Allow it, or type instead.'
          : 'Voice needs HTTPS.';
        err.classList.remove('d-none');
      }
    });
  }

  function pauseRec() {
    if (!rec.recording) return;
    rec.paused = !rec.paused;
    if (rec.paused) {
      rec.elapsed += Date.now() - rec.started;
      try { if (rec.sr) rec.sr.stop(); } catch (e) {}
      try { if (rec.mr && rec.mr.state === 'recording') rec.mr.pause(); } catch (e) {}
      document.getElementById('tv-vj-pause').textContent = 'Resume';
      recorderEl.classList.remove('is-live');
    } else {
      rec.started = Date.now();
      startSpeech();
      try { if (rec.mr && rec.mr.state === 'paused') rec.mr.resume(); } catch (e) {}
      document.getElementById('tv-vj-pause').textContent = 'Pause';
      recorderEl.classList.add('is-live');
    }
  }

  function stopRec() {
    rec.elapsed += rec.recording && !rec.paused ? Date.now() - rec.started : 0;
    rec.recording = false;
    rec.paused = false;
    clearInterval(rec.timer);
    try { if (rec.sr) rec.sr.stop(); } catch (e) {}
    try { if (rec.mr && rec.mr.state !== 'inactive') rec.mr.stop(); } catch (e) {}
    stopTracks();
    setLive(false);
    document.getElementById('tv-vj-pause').textContent = 'Pause';
    document.getElementById('tv-vj-pause').disabled = true;
    document.getElementById('tv-vj-stop').disabled = true;
    finishText(rec.text);
    tick();
  }

  function resetRec() {
    stopRec();
    rec.text = '';
    rec.chunks = [];
    if (rec.blobUrl) { URL.revokeObjectURL(rec.blobUrl); rec.blobUrl = ''; }
    if (liveEl) liveEl.textContent = '';
    var box = document.getElementById('tv-vj-rec-confirm');
    if (box) box.classList.add('d-none');
    var audio = document.getElementById('tv-vj-audio');
    if (audio) audio.removeAttribute('src');
    var t = document.getElementById('tv-vj-timer');
    if (t) t.textContent = '0:00';
  }

  /* ---------- screenshots ---------- */
  function bindShot(which) {
    var input = document.getElementById(which + '_screenshot');
    var preview = document.getElementById('tv-vj-' + which + '-preview');
    var empty = document.getElementById('tv-vj-' + which + '-empty');
    if (!input) return;
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) return;
      var url = URL.createObjectURL(file);
      if (which === 'before') beforeUrl = url; else afterUrl = url;
      if (preview) {
        preview.src = url;
        preview.classList.remove('d-none');
      }
      if (empty) empty.classList.add('d-none');
      document.querySelectorAll('[data-replace="' + which + '"],[data-remove="' + which + '"]').forEach(function (b) {
        b.classList.remove('d-none');
      });
      if (which === 'before') extractShot(file);
    });
  }

  function extractShot(file) {
    if (!boot.extractUrl) return;
    var fd = new FormData();
    fd.append('image', file, file.name || 'chart.jpg');
    fetch(boot.extractUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf() },
      body: fd
    }).then(function (r) { return r.json(); }).then(function (data) {
      extracted = (data && data.fields) || {};
      if (data && data.instrument) extracted._instrument = data.instrument;
      if (extractedHasValues()) {
        applyParsed(extracted, data.instrument);
        confirmed.prices = false;
        confirmed.symbol = false;
      }
    }).catch(function () {});
  }

  function renderFound() {
    var el = document.getElementById('tv-vj-found');
    if (!el) return;
    var parts = [];
    var inst = extracted.symbol || val('symbol');
    var side = extracted.trade_type || val('trade_type');
    if (inst || side) parts.push('<div class="fw-bold mb-2">' + esc(inst || '—') + ' · ' + esc(side || '—') + '</div>');
    parts.push('<div class="small">Entry: <strong>' + esc(extracted.entry_price || val('entry_price') || '—') + '</strong></div>');
    parts.push('<div class="small">Stop Loss: <strong>' + esc(extracted.stop_loss || val('stop_loss') || '—') + '</strong></div>');
    parts.push('<div class="small">Take Profit: <strong>' + esc(extracted.take_profit || val('take_profit') || '—') + '</strong></div>');
    parts.push('<p class="small tv-muted mb-0 mt-2">Is everything correct?</p>');
    el.innerHTML = parts.join('');
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c];
    });
  }

  function suggestSessionUI() {
    var sug = (boot.session || {}).session_type;
    if (!sug) return;
    document.querySelectorAll('#tv-vj-session-chips [data-session]').forEach(function (btn) {
      if (btn.getAttribute('data-session') === sug) btn.classList.add('is-on');
    });
    if (!val('session_type')) {
      setVal('session_type', sug);
      setVal('guide_session', sug);
    }
  }

  function maybeSymbolConfirm() {
    var card = document.getElementById('tv-vj-symbol-confirm');
    if (!card) return;
    if (val('symbol') && !confirmed.symbol) {
      card.classList.remove('d-none');
      card.innerHTML = 'I heard “<strong>' + esc(val('symbol')) + '</strong>”. Is that correct?';
    } else {
      card.classList.add('d-none');
    }
  }

  function metricsHtml() {
    var entry = parseFloat(val('entry_price'));
    var sl = parseFloat(val('stop_loss'));
    var tp = parseFloat(val('take_profit'));
    var lot = parseFloat(val('lot_size') || '1') || 1;
    var side = val('trade_type') || 'BUY';
    var bits = [];
    if (entry && sl) {
      var risk = Math.abs(entry - sl) * lot;
      bits.push(['Risk', '$' + risk.toFixed(2)]);
    }
    if (entry && tp) {
      var rew = Math.abs(tp - entry) * lot;
      bits.push(['Target', '$' + rew.toFixed(2)]);
    }
    if (entry && sl && tp) {
      var r = side === 'SELL' ? (sl - entry) : (entry - sl);
      var w = side === 'SELL' ? (entry - tp) : (tp - entry);
      if (r > 0 && w > 0) bits.push(['RR', '1:' + (w / r).toFixed(2).replace(/\.00$/, '')]);
    }
    return bits;
  }

  function renderSummary() {
    var el = document.getElementById('tv-vj-summary');
    if (!el) return;
    var rows = [
      ['Instrument', val('symbol') || '—'],
      ['Side', val('trade_type') || '—'],
      ['Session', val('session_type') || '—'],
      ['Entry', val('entry_price') || '—'],
      ['Stop Loss', val('stop_loss') || '—'],
      ['Take Profit', val('take_profit') || '—']
    ];
    if (isClosed()) rows.push(['Exit', val('exit_price') || '—']);
    metricsHtml().forEach(function (m) { rows.push(m); });
    if (val('guide_emotions')) rows.push(['Emotion', val('guide_emotions')]);
    if (val('guide_setup_tags')) rows.push(['Setup', val('guide_setup_tags')]);
    if (val('guide_why')) rows.push(['Why', val('guide_why')]);
    var html = '<div class="fw-bold mb-2">' + esc(val('symbol') || 'Trade') + ' · ' + esc(val('trade_type') || '') + '</div><dl>';
    rows.forEach(function (r) {
      html += '<dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd>';
    });
    html += '</dl>';
    if (beforeUrl || afterUrl) {
      html += '<div class="tv-vj-shots">';
      if (beforeUrl) html += '<img src="' + beforeUrl + '" alt="Before">';
      if (afterUrl) html += '<img src="' + afterUrl + '" alt="After">';
      html += '</div>';
    }
    html += '<button type="button" class="btn btn-sm btn-outline-secondary mt-3" id="tv-vj-edit-any">Edit</button>';
    el.innerHTML = html;
    var edit = document.getElementById('tv-vj-edit-any');
    if (edit) edit.addEventListener('click', function () {
      confirmed = {};
      idx = 0;
      paint();
    });
  }

  /* ---------- drafts ---------- */
  function snapshot() {
    var ids = ['symbol', 'instrument_id', 'trade_type', 'lot_size', 'entry_price', 'stop_loss', 'take_profit', 'exit_price', 'trade_log_status', 'session_type', 'strategy', 'emotion', 'guide_why', 'guide_emotions', 'guide_setup_tags', 'guide_session', 'guide_reflection', 'guide_voice_dump', 'guide_followed_plan', 'guide_moved_sl', 'guide_early_close', 'guide_partials', 'guide_added'];
    var data = { mode: mode, idx: idx, confirmed: confirmed, extracted: extracted };
    ids.forEach(function (id) { data[id] = val(id); });
    return data;
  }

  function saveDraft() {
    try {
      var data = snapshot();
      data.savedAt = Date.now();
      if (!data.symbol && !data.guide_voice_dump && !data.entry_price) {
        localStorage.removeItem(DRAFT_KEY);
        return;
      }
      localStorage.setItem(DRAFT_KEY, JSON.stringify(data));
    } catch (e) {}
  }

  function loadDraft() {
    try {
      return JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
    } catch (e) {
      return null;
    }
  }

  function applyDraft(data) {
    if (!data) return;
    restoring = true;
    Object.keys(data).forEach(function (k) {
      if (['mode', 'idx', 'confirmed', 'extracted', 'savedAt'].indexOf(k) !== -1) return;
      if (document.getElementById(k)) setVal(k, data[k]);
    });
    mode = data.mode === 'quick' ? 'quick' : 'full';
    confirmed = data.confirmed || {};
    extracted = data.extracted || {};
    fillPricesFromHidden();
    syncDir();
    restoring = false;
    idx = 0;
    paint();
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  }

  function draftBanner() {
    var data = loadDraft();
    var el = document.getElementById('tv-vj-draft-banner');
    if (!el || !data || !data.symbol) return;
    var meta = document.getElementById('tv-vj-draft-meta');
    var filled = ['symbol', 'entry_price', 'guide_why', 'session_type'].filter(function (k) { return data[k]; }).length;
    if (meta) meta.textContent = (data.symbol || 'Draft') + ' · ' + Math.round((filled / 6) * 100) + '% complete';
    el.classList.remove('d-none');
    document.getElementById('tv-vj-draft-continue').addEventListener('click', function () {
      el.classList.add('d-none');
      applyDraft(data);
    });
    document.getElementById('tv-vj-draft-discard').addEventListener('click', function () {
      clearDraft();
      el.classList.add('d-none');
    });
  }

  function syncDir() {
    var v = val('trade_type');
    var buy = document.getElementById('tv-dir-buy');
    var sell = document.getElementById('tv-dir-sell');
    if (buy) buy.classList.toggle('is-on', v === 'BUY');
    if (sell) sell.classList.toggle('is-on', v === 'SELL');
  }

  /* ---------- events ---------- */
  document.getElementById('tv-vj-start-full') && document.getElementById('tv-vj-start-full').addEventListener('click', function () {
    mode = 'full';
    idx = 1;
    paint();
  });
  document.getElementById('tv-vj-start-quick') && document.getElementById('tv-vj-start-quick').addEventListener('click', function () {
    mode = 'quick';
    idx = 0;
    paint();
  });
  document.getElementById('tv-vj-welcome-mic') && document.getElementById('tv-vj-welcome-mic').addEventListener('click', function () {
    mode = 'full';
    idx = 1;
    paint();
    startRec();
  });

  if (nextBtn) nextBtn.addEventListener('click', function () { go(1); });
  if (backBtn) backBtn.addEventListener('click', function () { go(-1); });
  if (skipBtn) skipBtn.addEventListener('click', function () {
    bumpSkip(currentKey());
    idx += 1;
    paint();
  });

  var micBtn = document.getElementById('tv-vj-mic');
  if (micBtn) micBtn.addEventListener('click', function () {
    if (rec.recording) stopRec();
    else startRec();
  });
  document.getElementById('tv-vj-pause') && document.getElementById('tv-vj-pause').addEventListener('click', pauseRec);
  document.getElementById('tv-vj-stop') && document.getElementById('tv-vj-stop').addEventListener('click', stopRec);
  document.getElementById('tv-vj-replay') && document.getElementById('tv-vj-replay').addEventListener('click', function () {
    var a = document.getElementById('tv-vj-audio');
    if (a && rec.blobUrl) { a.classList.remove('d-none'); a.play(); }
  });
  document.getElementById('tv-vj-delete-rec') && document.getElementById('tv-vj-delete-rec').addEventListener('click', resetRec);
  document.getElementById('tv-vj-retry') && document.getElementById('tv-vj-retry').addEventListener('click', function () {
    resetRec();
    startRec();
  });
  document.getElementById('tv-vj-accept') && document.getElementById('tv-vj-accept').addEventListener('click', function () {
    var text = rec.text;
    var key = currentKey();
    if (key === 'why') setVal('guide_why', text);
    if (key === 'reflection') setVal('guide_reflection', text);
    if (key === 'emotions') setVal('guide_feeling_before', text);
    if (key === 'talk') setVal('guide_voice_dump', text);
    parseTranscript(text).then(function () {
      if (key === 'symbol' && val('symbol') && !val('instrument_id')) confirmed.symbol = false;
      if (key === 'symbol' && val('instrument_id')) confirmed.symbol = !val('symbol') ? false : confirmed.symbol;
      go(1);
    });
  });

  document.querySelectorAll('[data-dir]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setVal('trade_type', btn.getAttribute('data-dir'));
      confirmed.side = true;
      syncDir();
      go(1);
    });
  });
  document.querySelectorAll('[data-status]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setVal('trade_log_status', btn.getAttribute('data-status'));
      go(1);
    });
  });
  document.querySelectorAll('[data-plan]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setVal('guide_followed_plan', btn.getAttribute('data-plan'));
      document.querySelectorAll('[data-plan]').forEach(function (b) { b.classList.toggle('is-on', b === btn); });
    });
  });
  document.querySelectorAll('#tv-vj-session-chips [data-session]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setVal('session_type', btn.getAttribute('data-session'));
      setVal('guide_session', btn.getAttribute('data-session'));
      document.querySelectorAll('#tv-vj-session-chips [data-session]').forEach(function (b) { b.classList.toggle('is-on', b === btn); });
    });
  });
  document.querySelectorAll('#tv-vj-emotion-chips [data-emotion]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.classList.toggle('is-on');
      var picked = [];
      document.querySelectorAll('#tv-vj-emotion-chips [data-emotion].is-on').forEach(function (b) {
        picked.push(b.getAttribute('data-emotion'));
      });
      setVal('guide_emotions', picked.join(', '));
      if (picked[0]) {
        setVal('guide_feeling_before', picked[0]);
        setVal('emotion', picked[0]);
      }
    });
  });
  document.querySelectorAll('#tv-vj-setup-chips [data-setup]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.classList.toggle('is-on');
      var picked = [];
      document.querySelectorAll('#tv-vj-setup-chips [data-setup].is-on').forEach(function (b) {
        picked.push(b.getAttribute('data-setup'));
      });
      setVal('guide_setup_tags', picked.join(', '));
    });
  });
  document.querySelectorAll('#tv-vj-mgmt .tv-vj-yn-row').forEach(function (row) {
    row.querySelectorAll('.tv-vj-yn-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        row.querySelectorAll('.tv-vj-yn-btn').forEach(function (b) { b.classList.remove('is-on'); });
        btn.classList.add('is-on');
        var key = row.getAttribute('data-mgmt');
        var map = { moved_sl: 'guide_moved_sl', early_close: 'guide_early_close', partials: 'guide_partials', added: 'guide_added' };
        if (map[key]) setVal(map[key], btn.getAttribute('data-val'));
      });
    });
  });

  document.querySelectorAll('[data-pick],[data-replace]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var which = btn.getAttribute('data-pick') || btn.getAttribute('data-replace');
      var input = document.getElementById(which + '_screenshot');
      if (input) input.click();
    });
  });
  document.querySelectorAll('[data-remove]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var which = btn.getAttribute('data-remove');
      var input = document.getElementById(which + '_screenshot');
      if (input) input.value = '';
      var preview = document.getElementById('tv-vj-' + which + '-preview');
      var empty = document.getElementById('tv-vj-' + which + '-empty');
      if (preview) { preview.classList.add('d-none'); preview.removeAttribute('src'); }
      if (empty) empty.classList.remove('d-none');
      btn.classList.add('d-none');
      var rep = document.querySelector('[data-replace="' + which + '"]');
      if (rep) rep.classList.add('d-none');
      if (which === 'before') { beforeUrl = ''; extracted = {}; }
      else afterUrl = '';
    });
  });
  document.querySelectorAll('.tv-vj-upload').forEach(function (zone) {
    zone.addEventListener('dragover', function (e) { e.preventDefault(); });
    zone.addEventListener('drop', function (e) {
      e.preventDefault();
      var which = zone.getAttribute('data-shot');
      var input = document.getElementById(which + '_screenshot');
      if (input && e.dataTransfer.files && e.dataTransfer.files[0]) {
        input.files = e.dataTransfer.files;
        input.dispatchEvent(new Event('change'));
      }
    });
  });
  bindShot('before');
  bindShot('after');

  document.getElementById('tv-vj-found-yes') && document.getElementById('tv-vj-found-yes').addEventListener('click', function () {
    confirmed.prices = true;
    confirmed.symbol = true;
    confirmed.side = true;
    if (extracted._instrument) applyInstrument(extracted._instrument.id, extracted._instrument.symbol, extracted._instrument.name);
    go(1);
  });
  document.getElementById('tv-vj-found-edit') && document.getElementById('tv-vj-found-edit').addEventListener('click', function () {
    confirmed.prices = false;
    fillPricesFromHidden();
    var list = steps();
    idx = Math.max(0, list.indexOf('prices'));
    paint();
  });

  form.addEventListener('submit', function (ev) {
    if (currentKey() !== 'confirm') {
      ev.preventDefault();
      go(1);
      return;
    }
    syncVisibleInputs();
    var msg = validate('symbol') || (isClosed() ? validate('exit') : '') || validate('prices');
    if (msg) {
      ev.preventDefault();
      showErr(msg);
      return;
    }
    if (!val('lot_size')) setVal('lot_size', '1');
    var why = val('guide_why') || val('guide_voice_dump');
    if (why && !val('pre_trade_plan')) setVal('pre_trade_plan', why);
    var post = val('guide_what_happened') || val('guide_reflection') || val('guide_voice_dump');
    if (post && !val('post_trade_notes')) setVal('post_trade_notes', post);
    clearDraft();
  });

  document.addEventListener('tv-instrument-selected', function (ev) {
    confirmed.symbol = true;
    if (ev.detail && ev.detail.symbol) setVal('symbol', ev.detail.symbol);
  });

  if (typeof SimpleInstrumentPicker === 'function') {
    window.simpleInstrumentPicker = new SimpleInstrumentPicker();
  }

  if (boot.complete) {
    confirmed.symbol = true;
    confirmed.side = true;
    confirmed.prices = true;
    if (boot.complete.status === 'CLOSED') setVal('trade_log_status', 'closed');
    fillPricesFromHidden();
  }
  if (boot.mode === 'quick') mode = 'quick';

  draftBanner();
  syncDir();
  fillPricesFromHidden();
  paint();

  window.addEventListener('pagehide', saveDraft);
})();
