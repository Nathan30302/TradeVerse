/**
 * Voice Journal — ask → listen → fill → next. Same Trade POST as Log Trade.
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

  var FULL = ['symbol', 'direction', 'status', 'before_shot', 'shot_confirm', 'entry', 'stop_loss', 'take_profit', 'exit', 'why', 'emotions', 'after_shot', 'confirm'];
  var QUICK = ['before_shot', 'shot_confirm', 'talk', 'confirm'];

  var mode = boot.mode === 'quick' ? 'quick' : 'full';
  var started = false;
  var skipped = {};
  var misses = {};
  var extracted = {};
  var confirmed = {};
  var beforeUrl = '';
  var afterUrl = '';
  var lastAsked = '';
  var restoring = false;
  var pickerReady = false;
  var committing = false;

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
  var heardEl = document.getElementById('tv-vj-heard');
  var capturedEl = document.getElementById('tv-vj-captured');

  var COPY = {
    welcome: ['Let’s log your trade.', 'Just talk. I’ll guide you through it.'],
    symbol: ['What did you trade?', 'Say the pair — gold, EURUSD, NAS100…'],
    direction: ['Buy or sell?', 'Just say it.'],
    status: ['Still open, or already done?', 'Say open, or closed.'],
    before_shot: ['Upload the before-trade screenshot.', 'I’ll read the levels from the chart.'],
    shot_confirm: ['I found these details. Correct?', 'Say yes, or say change.'],
    entry: ['What was your entry?', 'Say the number.'],
    stop_loss: ['What was your stop loss?', 'Say the number.'],
    take_profit: ['What was your take profit?', 'Say the number.'],
    exit: ['Where did you get out?', 'Say the fill.'],
    talk: ['Tell me what happened.', 'Instrument, side, levels, why — I’ll sort it.'],
    why: ['Why did you take this trade?', 'One sentence is enough.'],
    emotions: ['How were you feeling?', 'Say it naturally.'],
    after_shot: ['Now the after-trade screenshot.', 'Before → after is the journal.'],
    confirm: ['Trade ready.', 'Check it, then save.']
  };

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
    gen: 0
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
    if (el) el.value = value == null ? '' : String(value);
  }

  function isClosed() {
    return val('trade_log_status') === 'closed';
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

  function extractedHasValues() {
    return !!(extracted.symbol || extracted.trade_type || extracted.entry_price || extracted.stop_loss || extracted.take_profit);
  }

  function isFilled(key) {
    if (skipped[key]) return true;
    if (key === 'symbol') return !!(val('instrument_id') && val('symbol'));
    if (key === 'direction') return !!confirmed.side && (val('trade_type') === 'BUY' || val('trade_type') === 'SELL');
    if (key === 'status') return !!confirmed.status;
    if (key === 'before_shot') return false;
    if (key === 'shot_confirm') return !extractedHasValues() || !!confirmed.extract;
    if (key === 'entry') return !!val('entry_price');
    if (key === 'stop_loss') return !!val('stop_loss') || !!skipped.stop_loss;
    if (key === 'take_profit') return !!val('take_profit') || !!skipped.take_profit;
    if (key === 'exit') return !isClosed() || !!val('exit_price');
    if (key === 'talk') return !!val('guide_voice_dump');
    if (key === 'why') return !!val('guide_why');
    if (key === 'emotions') return !!val('guide_emotions') || !!skipped.emotions;
    if (key === 'after_shot') return !isClosed();
    if (key === 'confirm') return false;
    return false;
  }

  function optionalStep(key) {
    return ['before_shot', 'after_shot', 'stop_loss', 'take_profit', 'why', 'emotions', 'talk'].indexOf(key) !== -1;
  }

  function voiceStep(key) {
    return ['symbol', 'direction', 'status', 'shot_confirm', 'entry', 'stop_loss', 'take_profit', 'exit', 'talk', 'why', 'emotions'].indexOf(key) !== -1;
  }

  function queue() {
    var list = mode === 'quick' ? QUICK.slice() : FULL.slice();
    return list.filter(function (key) { return !isFilled(key); });
  }

  function currentKey() {
    if (!started) return 'welcome';
    return queue()[0] || 'confirm';
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c];
    });
  }

  function renderCaptured() {
    if (!capturedEl) return;
    var bits = [];
    if (val('symbol')) bits.push(val('symbol'));
    if (confirmed.side) bits.push(val('trade_type'));
    if (confirmed.status) bits.push(isClosed() ? 'Closed' : 'Open');
    if (val('entry_price')) bits.push('In ' + val('entry_price'));
    capturedEl.textContent = bits.join(' · ');
  }

  function showHeard(text) {
    if (!heardEl) return;
    if (!text) {
      heardEl.classList.add('d-none');
      heardEl.textContent = '';
      return;
    }
    heardEl.textContent = 'Heard: “' + text + '”';
    heardEl.classList.remove('d-none');
  }

  function paint() {
    var key = currentKey();
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
    var list = queue();
    if (dotsEl) {
      dotsEl.textContent = '';
      var shown = (mode === 'quick' ? QUICK : FULL).filter(function (k) { return k !== 'confirm'; });
      var now = shown.indexOf(key);
      shown.forEach(function (k, i) {
        var d = document.createElement('span');
        if (isFilled(k) || (now !== -1 && i < now)) d.className = 'is-done';
        if (k === key) d.className = 'is-now';
        dotsEl.appendChild(d);
      });
    }
    if (progressLabel) {
      progressLabel.textContent = key === 'confirm' ? 'Ready to save.' : (list.length <= 3 ? 'Almost there.' : '');
    }
    var last = key === 'confirm';
    if (backBtn) backBtn.disabled = key === 'welcome';
    if (nextBtn) nextBtn.classList.toggle('d-none', last || voiceStep(key));
    if (saveBtn) saveBtn.classList.toggle('d-none', !last);
    if (skipBtn) skipBtn.classList.toggle('d-none', last || key === 'welcome' || !optionalStep(key));
    if (recorderEl) recorderEl.classList.toggle('d-none', !started || !voiceStep(key));
    document.querySelectorAll('.tv-vj-fallback').forEach(function (el) {
      var step = el.closest('.tv-vj-step');
      var sk = step ? step.getAttribute('data-step') : '';
      el.classList.toggle('d-none', !(misses[sk] >= 1 && sk === key));
    });
    if (key === 'shot_confirm') renderFound();
    if (last) renderSummary();
    renderCaptured();
    showErr('');
    if (!restoring) saveDraft();
    if (started && voiceStep(key) && key !== lastAsked && !rec.recording && !committing) {
      lastAsked = key;
      askThenListen(copy[0]);
    }
  }

  function stopTTS() {
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) {}
  }

  function askThenListen(question) {
    stopRec(true);
    stopTTS();
    var spoken = false;
    function listen() {
      setTimeout(function () {
        if (started && voiceStep(currentKey())) startRec();
      }, 350);
    }
    if (window.speechSynthesis && question) {
      try {
        var u = new SpeechSynthesisUtterance(question);
        u.rate = 1.04;
        u.pitch = 1;
        spoken = true;
        u.onend = listen;
        u.onerror = listen;
        window.speechSynthesis.speak(u);
      } catch (e) {
        spoken = false;
      }
    }
    if (!spoken) listen();
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
    return navigator.mediaDevices.getUserMedia({ audio: true, video: false }).then(function (stream) {
      rec.stream = stream;
      return stream;
    });
  }

  function setLive(on) {
    rec.recording = !!on;
    if (recorderEl) recorderEl.classList.toggle('is-live', !!on);
    var mic = document.getElementById('tv-vj-mic');
    if (mic) mic.classList.toggle('is-live', !!on);
    var icon = document.getElementById('tv-vj-mic-icon');
    if (icon) icon.className = on ? 'fas fa-stop' : 'fas fa-microphone';
    var timer = document.getElementById('tv-vj-timer');
    if (timer) timer.textContent = on ? 'Listening… tap when you’re done' : 'Tap to speak';
  }

  function watchLoudness(stream) {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      if (!rec.ctx) rec.ctx = new AC();
      if (rec.ctx.state === 'suspended') rec.ctx.resume();
      if (!rec.srcNode) {
        rec.srcNode = rec.ctx.createMediaStreamSource(stream);
        rec.analyser = rec.ctx.createAnalyser();
        rec.analyser.fftSize = 512;
        rec.srcNode.connect(rec.analyser);
      }
      var analyser = rec.analyser;
      var data = new Uint8Array(analyser.fftSize);
      var quiet = 0;
      var heard = false;
      clearInterval(rec.loudWatch);
      rec.loudWatch = setInterval(function () {
        if (!rec.recording) {
          clearInterval(rec.loudWatch);
          return;
        }
        analyser.getByteTimeDomainData(data);
        var sum = 0;
        for (var i = 0; i < data.length; i++) {
          var v = (data[i] - 128) / 128;
          sum += v * v;
        }
        var rms = Math.sqrt(sum / data.length);
        if (rms > 0.055) {
          heard = true;
          quiet = 0;
        } else {
          quiet += 100;
        }
        if (heard && quiet >= 2000) stopRec(false);
        else if (!heard && quiet >= 5500) stopRec(false);
      }, 100);
    } catch (e) { /* ignore */ }
  }

  function armSilence() {
    clearTimeout(rec.silence);
    if (!rec.text) return;
    rec.silence = setTimeout(function () {
      if (rec.recording && rec.text) stopRec(false);
    }, 1400);
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
        if (liveEl) liveEl.textContent = rec.text || interim || 'Listening…';
        if (rec.text || interim) armSilence();
      };
      rec.sr.onerror = function () { /* Whisper still running */ };
      rec.sr.start();
      return true;
    } catch (e) {
      return false;
    }
  }

  function startRec() {
    if (rec.recording || committing) return;
    var err = document.getElementById('tv-vj-mic-err');
    if (err) { err.classList.add('d-none'); err.textContent = ''; }
    rec.text = '';
    rec.chunks = [];
    rec.gen += 1;
    var gen = rec.gen;
    if (liveEl) liveEl.textContent = 'Listening…';
    ensureStream().then(function (stream) {
      if (gen !== rec.gen) return;
      rec.mime = pickMime();
      try {
        rec.mr = rec.mime ? new MediaRecorder(stream, { mimeType: rec.mime }) : new MediaRecorder(stream);
      } catch (e) {
        rec.mr = new MediaRecorder(stream);
      }
      rec.mr.ondataavailable = function (e) {
        if (e.data && e.data.size) rec.chunks.push(e.data);
      };
      try { rec.mr.start(250); } catch (e) { rec.mr.start(); }
      startSpeech();
      setLive(true);
      watchLoudness(stream);
      clearTimeout(rec.maxTimer);
      rec.maxTimer = setTimeout(function () {
        if (rec.recording) stopRec(false);
      }, currentKey() === 'why' || currentKey() === 'talk' ? 25000 : 12000);
    }).catch(function () {
      if (err) {
        err.textContent = window.isSecureContext
          ? 'Allow the microphone, then tap the button again.'
          : 'Voice needs HTTPS.';
        err.classList.remove('d-none');
      }
      misses[currentKey()] = (misses[currentKey()] || 0) + 1;
      paint();
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
    setLive(false);
    try { if (rec.sr) rec.sr.stop(); } catch (e) {}
    rec.sr = null;
    var mr = rec.mr;
    rec.mr = null;
    var gen = rec.gen;
    if (!mr) {
      if (!silent) finishUtterance(rec.text, null);
      return;
    }
    mr.onstop = function () {
      if (gen !== rec.gen) return;
      var blob = rec.chunks.length ? new Blob(rec.chunks, { type: rec.mime || mr.mimeType || 'audio/webm' }) : null;
      rec.chunks = [];
      if (silent) return;
      finishUtterance(rec.text, blob);
    };
    try {
      if (mr.state !== 'inactive') mr.stop();
      else if (!silent) finishUtterance(rec.text, null);
    } catch (e) {
      if (!silent) finishUtterance(rec.text, null);
    }
  }

  function finishUtterance(srText, blob) {
    var local = String(srText || '').trim();
    if (liveEl) liveEl.textContent = local ? ('“' + local + '”') : 'Working it out…';
    var useWhisper = !!(blob && blob.size > 400 && boot.transcribeEnabled);
    if (!useWhisper) {
      if (local) commitAnswer(local);
      else missAndRetry();
      return;
    }
    committing = true;
    var fd = new FormData();
    fd.append('audio', blob, blobName(blob.type || rec.mime));
    fetch(boot.transcribeUrl || '/api/voice/transcribe', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf() },
      body: fd
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        committing = false;
        var whispered = res && res.d && res.d.text ? String(res.d.text).trim() : '';
        var text = whispered || local;
        if (text) commitAnswer(text);
        else missAndRetry(res && res.d && res.d.error);
      })
      .catch(function () {
        committing = false;
        if (local) commitAnswer(local);
        else missAndRetry();
      });
  }

  function missAndRetry(msg) {
    var key = currentKey();
    misses[key] = (misses[key] || 0) + 1;
    showErr(msg || 'I didn’t catch that. Say it again — or tap an option below.');
    paint();
    if (voiceStep(key) && misses[key] < 3) {
      setTimeout(function () { if (currentKey() === key) startRec(); }, 500);
    }
  }

  function applyInstrument(id, symbol, name) {
    setVal('instrument_id', id);
    setVal('symbol', symbol);
    if (window.simpleInstrumentPicker && window.simpleInstrumentPicker.selectInstrument) {
      try { window.simpleInstrumentPicker.selectInstrument(id, symbol, name || symbol); } catch (e) {}
    }
  }

  function applyParsed(parsed, instrument) {
    if (!parsed) return;
    if (instrument && instrument.id) applyInstrument(instrument.id, instrument.symbol, instrument.name);
    else if (parsed.symbol) setVal('symbol', parsed.symbol);
    if (parsed.trade_type) {
      setVal('trade_type', parsed.trade_type);
      confirmed.side = true;
    }
    if (parsed.status === 'open' || parsed.status === 'closed') {
      setVal('trade_log_status', parsed.status);
      confirmed.status = true;
    }
    ['entry_price', 'stop_loss', 'take_profit', 'exit_price', 'lot_size'].forEach(function (k) {
      if (parsed[k] != null && parsed[k] !== '') setVal(k, parsed[k]);
    });
    if (parsed.session_type) {
      setVal('session_type', parsed.session_type);
      setVal('guide_session', parsed.session_type);
    }
    if (parsed.emotions && parsed.emotions.length) {
      setVal('guide_emotions', parsed.emotions.join(', '));
      setVal('guide_feeling_before', parsed.emotions[0]);
      setVal('emotion', parsed.emotions[0]);
    }
    if (parsed.setup_tags && parsed.setup_tags.length) {
      setVal('guide_setup_tags', parsed.setup_tags.join(', '));
    }
  }

  function takeNumber(parsed, text) {
    if (parsed && parsed.bare_number != null) return parsed.bare_number;
    var m = String(text || '').replace(/,/g, '').match(/(\d+(?:\.\d+)?)/);
    return m ? m[1] : '';
  }

  function resolveSymbol(parsed, instrument) {
    if (instrument && instrument.id) {
      applyInstrument(instrument.id, instrument.symbol, instrument.name);
      return Promise.resolve(true);
    }
    var q = (parsed && parsed.symbol) || val('symbol');
    if (!q) return Promise.resolve(false);
    return fetch('/api/db/instruments/search?q=' + encodeURIComponent(q) + '&limit=5')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var row = (data && data.results && data.results[0]) || null;
        if (!row) return false;
        applyInstrument(row.id, row.symbol, row.name);
        return true;
      })
      .catch(function () { return false; });
  }

  function stepSatisfied(key, parsed, text) {
    var t = String(text || '').trim();
    if (key === 'symbol') return !!(val('instrument_id') && val('symbol'));
    if (key === 'direction') return !!confirmed.side;
    if (key === 'status') return !!confirmed.status;
    if (key === 'shot_confirm') return !!confirmed.extract;
    if (key === 'entry') return !!val('entry_price');
    if (key === 'stop_loss') return !!val('stop_loss');
    if (key === 'take_profit') return !!val('take_profit');
    if (key === 'exit') return !!val('exit_price');
    if (key === 'talk' || key === 'why') return t.length >= 4;
    if (key === 'emotions') return !!val('guide_emotions') || t.length >= 3;
    return false;
  }

  function looksLikeEcho(text) {
    var q = ((COPY[currentKey()] || [])[0] || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    var a = String(text || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    if (!a || !q || a.length < 8) return false;
    return a === q || a.indexOf(q) !== -1 || (a.length > 10 && q.indexOf(a) !== -1);
  }

  function commitAnswer(text) {
    var key = currentKey();
    if (looksLikeEcho(text)) {
      missAndRetry();
      return;
    }
    showHeard(text);
    if (liveEl) liveEl.textContent = '“' + text + '”';
    committing = true;
    parseTranscript(text, key).then(function (data) {
      var parsed = (data && data.parsed) || {};
      applyParsed(parsed, data && data.instrument);

      if (key === 'direction' && parsed.trade_type) confirmed.side = true;
      if (key === 'status') {
        if (parsed.status) {
          setVal('trade_log_status', parsed.status);
          confirmed.status = true;
        } else if (/open|still/i.test(text)) {
          setVal('trade_log_status', 'open');
          confirmed.status = true;
        } else if (/close|done|finish/i.test(text)) {
          setVal('trade_log_status', 'closed');
          confirmed.status = true;
        }
      }
      if (key === 'shot_confirm') {
        if (parsed.yes_no === 'yes' || /^\s*y/i.test(text)) confirmed.extract = true;
        if (parsed.yes_no === 'no' || /change|wrong|edit/i.test(text)) {
          confirmed.extract = false;
          skipped.shot_confirm = true;
          committing = false;
          paint();
          return;
        }
      }
      if (key === 'entry' && !val('entry_price')) setVal('entry_price', takeNumber(parsed, text));
      if (key === 'stop_loss' && !val('stop_loss')) setVal('stop_loss', takeNumber(parsed, text));
      if (key === 'take_profit' && !val('take_profit')) setVal('take_profit', takeNumber(parsed, text));
      if (key === 'exit' && !val('exit_price')) setVal('exit_price', takeNumber(parsed, text));
      if (key === 'why' || key === 'talk') {
        setVal('guide_why', val('guide_why') || text);
        setVal('guide_voice_dump', text);
      }
      if (key === 'emotions') {
        setVal('guide_emotions', val('guide_emotions') || text);
        setVal('guide_feeling_before', val('guide_feeling_before') || text);
      }

      var done = Promise.resolve(true);
      if (key === 'symbol' && !val('instrument_id')) {
        done = resolveSymbol(parsed, data && data.instrument);
      }
      return done.then(function () {
        committing = false;
        if (stepSatisfied(key, parsed, text)) {
          misses[key] = 0;
          paint();
        } else {
          missAndRetry();
        }
      });
    }).catch(function () {
      committing = false;
      missAndRetry();
    });
  }

  function parseTranscript(text, focus) {
    if (!text || !boot.parseUrl) return Promise.resolve(null);
    return fetch(boot.parseUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), 'X-CSRF-Token': csrf() },
      body: JSON.stringify({ text: text, focus: focus || '' })
    }).then(function (r) { return r.json(); });
  }

  function renderFound() {
    var el = document.getElementById('tv-vj-found');
    if (!el) return;
    el.innerHTML =
      '<div class="fw-bold mb-2">' + esc(extracted.symbol || val('symbol') || '—') + ' · ' +
      esc(extracted.trade_type || val('trade_type') || '—') + '</div>' +
      '<div class="small">Entry <strong>' + esc(extracted.entry_price || val('entry_price') || '—') + '</strong></div>' +
      '<div class="small">Stop <strong>' + esc(extracted.stop_loss || val('stop_loss') || '—') + '</strong></div>' +
      '<div class="small">Target <strong>' + esc(extracted.take_profit || val('take_profit') || '—') + '</strong></div>';
  }

  function renderSummary() {
    var el = document.getElementById('tv-vj-summary');
    if (!el) return;
    var rows = [
      ['Instrument', val('symbol') || '—'],
      ['Side', val('trade_type') || '—'],
      ['Status', isClosed() ? 'Closed' : 'Open'],
      ['Entry', val('entry_price') || '—'],
      ['Stop', val('stop_loss') || '—'],
      ['Target', val('take_profit') || '—']
    ];
    if (isClosed()) rows.push(['Exit', val('exit_price') || '—']);
    var entry = parseFloat(val('entry_price'));
    var sl = parseFloat(val('stop_loss'));
    var tp = parseFloat(val('take_profit'));
    if (entry && sl && tp) {
      var r = val('trade_type') === 'SELL' ? (sl - entry) : (entry - sl);
      var w = val('trade_type') === 'SELL' ? (entry - tp) : (tp - entry);
      if (r > 0 && w > 0) rows.push(['RR', '1:' + (w / r).toFixed(2).replace(/\.00$/, '')]);
    }
    if (val('guide_emotions')) rows.push(['Emotion', val('guide_emotions')]);
    if (val('guide_why')) rows.push(['Why', val('guide_why')]);
    var html = '<div class="fw-bold mb-2">' + esc(val('symbol') || 'Trade') + ' · ' + esc(val('trade_type') || '') + '</div><dl>';
    rows.forEach(function (row) {
      html += '<dt>' + esc(row[0]) + '</dt><dd>' + esc(row[1]) + '</dd>';
    });
    html += '</dl>';
    if (beforeUrl || afterUrl) {
      html += '<div class="tv-vj-shots">';
      if (beforeUrl) html += '<img src="' + beforeUrl + '" alt="Before">';
      if (afterUrl) html += '<img src="' + afterUrl + '" alt="After">';
      html += '</div>';
    }
    el.innerHTML = html;
  }

  function saveDraft() {
    try {
      if (!started && !val('symbol')) {
        localStorage.removeItem(DRAFT_KEY);
        return;
      }
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        started: started, mode: mode, skipped: skipped, confirmed: confirmed,
        symbol: val('symbol'), instrument_id: val('instrument_id'), trade_type: val('trade_type'),
        entry_price: val('entry_price'), stop_loss: val('stop_loss'), take_profit: val('take_profit'),
        exit_price: val('exit_price'), trade_log_status: val('trade_log_status'),
        guide_why: val('guide_why'), guide_emotions: val('guide_emotions'),
        guide_voice_dump: val('guide_voice_dump'), savedAt: Date.now()
      }));
    } catch (e) {}
  }

  function loadDraft() {
    try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); } catch (e) { return null; }
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
        confirmed.extract = false;
      }
      skipped.before_shot = true;
      paint();
    }).catch(function () {
      skipped.before_shot = true;
      paint();
    });
  }

  function bindShot(which) {
    var input = document.getElementById(which + '_screenshot');
    if (!input) return;
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) return;
      var url = URL.createObjectURL(file);
      if (which === 'before') beforeUrl = url; else afterUrl = url;
      var preview = document.getElementById('tv-vj-' + which + '-preview');
      var empty = document.getElementById('tv-vj-' + which + '-empty');
      if (preview) { preview.src = url; preview.classList.remove('d-none'); }
      if (empty) empty.classList.add('d-none');
      if (which === 'before') extractShot(file);
      else {
        skipped.after_shot = true;
        paint();
      }
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

  function begin(quick) {
    mode = quick ? 'quick' : 'full';
    unlockAudio();
    ensureStream().then(function () {
      started = true;
      paint();
    }).catch(function () {
      started = true;
      misses.symbol = 1;
      paint();
    });
  }

  document.getElementById('tv-vj-start-full') && document.getElementById('tv-vj-start-full').addEventListener('click', function () { begin(false); });
  document.getElementById('tv-vj-welcome-mic') && document.getElementById('tv-vj-welcome-mic').addEventListener('click', function () { begin(false); });
  document.getElementById('tv-vj-start-quick') && document.getElementById('tv-vj-start-quick').addEventListener('click', function () { begin(true); });

  document.getElementById('tv-vj-mic') && document.getElementById('tv-vj-mic').addEventListener('click', function () {
    if (rec.recording) stopRec(false);
    else startRec();
  });

  if (skipBtn) skipBtn.addEventListener('click', function () {
    skipped[currentKey()] = true;
    lastAsked = '';
    stopRec(true);
    stopTTS();
    paint();
  });
  if (backBtn) backBtn.addEventListener('click', function () {
    stopRec(true);
    stopTTS();
    lastAsked = '';
    var order = mode === 'quick' ? QUICK : FULL;
    var key = currentKey();
    var i = order.indexOf(key);
    if (i > 0) {
      var prev = order[i - 1];
      skipped[prev] = false;
      if (prev === 'symbol') { setVal('instrument_id', ''); setVal('symbol', ''); }
      if (prev === 'direction') confirmed.side = false;
      if (prev === 'status') confirmed.status = false;
    } else {
      started = false;
    }
    paint();
  });

  document.querySelectorAll('[data-dir]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setVal('trade_type', btn.getAttribute('data-dir'));
      confirmed.side = true;
      paint();
    });
  });
  document.querySelectorAll('[data-status]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setVal('trade_log_status', btn.getAttribute('data-status'));
      confirmed.status = true;
      paint();
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
      if (picked[0]) setVal('guide_feeling_before', picked[0]);
      if (picked.length) paint();
    });
  });
  document.getElementById('tv-vj-found-yes') && document.getElementById('tv-vj-found-yes').addEventListener('click', function () {
    confirmed.extract = true;
    if (extracted._instrument) applyInstrument(extracted._instrument.id, extracted._instrument.symbol, extracted._instrument.name);
    paint();
  });
  document.getElementById('tv-vj-found-edit') && document.getElementById('tv-vj-found-edit').addEventListener('click', function () {
    confirmed.extract = false;
    skipped.shot_confirm = true;
    paint();
  });

  ['tv-vj-entry', 'tv-vj-sl', 'tv-vj-tp', 'tv-vj-exit'].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', function () {
      var map = { 'tv-vj-entry': 'entry_price', 'tv-vj-sl': 'stop_loss', 'tv-vj-tp': 'take_profit', 'tv-vj-exit': 'exit_price' };
      if (el.value) setVal(map[id], el.value);
      paint();
    });
  });

  document.querySelectorAll('[data-pick]').forEach(function (btn) {
    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      var which = btn.getAttribute('data-pick');
      var input = document.getElementById(which + '_screenshot');
      if (input) input.click();
    });
  });
  bindShot('before');
  bindShot('after');

  document.addEventListener('tv-instrument-selected', function (ev) {
    if (ev.detail && ev.detail.symbol) setVal('symbol', ev.detail.symbol);
    paint();
  });

  form.addEventListener('submit', function (ev) {
    if (currentKey() !== 'confirm') {
      ev.preventDefault();
      return;
    }
    if (!val('lot_size')) setVal('lot_size', '1');
    var why = val('guide_why') || val('guide_voice_dump');
    if (why && !val('pre_trade_plan')) setVal('pre_trade_plan', why);
    var post = val('guide_reflection') || val('guide_voice_dump') || why;
    if (post && !val('post_trade_notes')) setVal('post_trade_notes', post);
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (err) {} });
    stopTTS();
  });

  var draft = loadDraft();
  if (draft && draft.symbol) {
    var banner = document.getElementById('tv-vj-draft-banner');
    if (banner) {
      banner.classList.remove('d-none');
      var meta = document.getElementById('tv-vj-draft-meta');
      if (meta) meta.textContent = draft.symbol + (draft.trade_type ? ' · ' + draft.trade_type : '');
      document.getElementById('tv-vj-draft-continue').addEventListener('click', function () {
        restoring = true;
        ['symbol', 'instrument_id', 'trade_type', 'entry_price', 'stop_loss', 'take_profit', 'exit_price', 'trade_log_status', 'guide_why', 'guide_emotions', 'guide_voice_dump'].forEach(function (k) {
          if (draft[k]) setVal(k, draft[k]);
        });
        confirmed = draft.confirmed || {};
        skipped = draft.skipped || {};
        mode = draft.mode === 'quick' ? 'quick' : 'full';
        started = true;
        banner.classList.add('d-none');
        restoring = false;
        ensureStream().then(function () { paint(); }).catch(function () { paint(); });
      });
      document.getElementById('tv-vj-draft-discard').addEventListener('click', function () {
        try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
        banner.classList.add('d-none');
      });
    }
  }

  if (boot.complete) {
    confirmed.side = true;
    confirmed.status = true;
    if (boot.complete.status === 'CLOSED') setVal('trade_log_status', 'closed');
  }
  if (boot.mode === 'quick') mode = 'quick';

  if (typeof SimpleInstrumentPicker === 'function') {
    window.simpleInstrumentPicker = new SimpleInstrumentPicker();
    pickerReady = true;
  }

  window.addEventListener('pagehide', function () {
    saveDraft();
    stopTTS();
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
  });

  paint();
})();
