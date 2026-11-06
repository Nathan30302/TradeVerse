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

  var VOICE_PRESETS = {
    marin: {
      label: 'Maya',
      rate: 0.96,
      pitch: 1,
      sample: 'Hey. I’m here. Tell me the trade.',
      names: ['sandy', 'shelley', 'flo', 'samantha', 'ava']
    },
    cedar: {
      label: 'Noah',
      rate: 0.94,
      pitch: 1,
      sample: 'Hey. Whenever you’re ready.',
      names: ['reed', 'rocko', 'daniel', 'evan', 'aaron']
    },
    sage: {
      label: 'Sage',
      rate: 0.95,
      pitch: 1,
      sample: 'Alright. I’m listening.',
      names: ['tessa', 'shelley', 'moira', 'fiona', 'serena']
    }
  };
  var JOKE_VOICES = /bad news|bahh|bells|boing|bubbles|cellos|good news|grandma|grandpa|jester|junior|organ|superstar|trinoids|wobble|zarvox|albert|fred|ralph|kathy/;
  var voiceId = 'marin';
  try {
    var savedVoice = localStorage.getItem('tv-vj-voice');
    if (savedVoice === 'coral') savedVoice = 'marin';
    if (savedVoice === 'ash') savedVoice = 'cedar';
    if (savedVoice && VOICE_PRESETS[savedVoice]) voiceId = savedVoice;
  } catch (e) {}

  var state = 'idle';
  var draft = {};
  var history = [];
  var transcriptDump = [];
  var hasShot = false;
  var hasBefore = false;
  var hasAfter = false;
  var shotKind = 'before';
  var skipShot = false;
  var committing = false;
  var lastReply = '';
  var lastMetrics = {};
  var fixField = '';
  var reviewMode = false;
  var storageKey = boot.storageKey || ('tv-vj-draft-' + (boot.userId || 'anon'));
  var journalSaved = false;
  var confirming = false;
  var audioCache = {};
  var voiceWarmOk = true;
  var typeInput = document.getElementById('tv-vj-type-input');
  var typeSend = document.getElementById('tv-vj-type-send');
  var chipHint = document.getElementById('tv-vj-chip-hint');
  var pendingEl = document.getElementById('tv-vj-pending');
  var progressEl = document.getElementById('tv-vj-progress');

  if (boot.mode === 'quick') {
    draft.voice_mode = 'quick';
  }

  function setPhase(phase) {
    if (!progressEl) return;
    var order = ['facts', 'reflect', 'charts', 'review'];
    var idx = order.indexOf(phase || 'facts');
    if (idx < 0) idx = 0;
    progressEl.querySelectorAll('[data-phase]').forEach(function (el) {
      var p = el.getAttribute('data-phase');
      var i = order.indexOf(p);
      el.classList.toggle('is-on', i === idx);
      el.classList.toggle('is-done', i >= 0 && i < idx);
    });
  }

  // Seed progress from restored draft / complete-trade deep link.
  try {
    if (boot.complete && boot.complete.symbol) setPhase('reflect');
    else if (draft && (draft.thesis_notes || draft.followed_plan)) setPhase('reflect');
    else if (draft && draft.symbol) setPhase('facts');
  } catch (e) { /* ignore */ }

  var rec = {
    stream: null,
    sr: null,
    mr: null,
    chunks: [],
    recording: false,
    text: '',
    live: '',
    base: '',
    lastHeardAt: 0,
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
    freq: null,
    voiceOn: false,
    voiceRms: 0,
    ripples: [],
    waterRipples: [],
    rippleAt: 0
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

  function voiceLabel() {
    return (VOICE_PRESETS[voiceId] || VOICE_PRESETS.marin).label;
  }

  function setState(next) {
    state = next;
    if (stage) stage.setAttribute('data-state', next);
    if (statusEl) {
      statusEl.textContent =
        next === 'listening' ? 'I’m with you' :
        next === 'thinking' ? 'Got it' :
        next === 'speaking' ? voiceLabel() :
        next === 'waiting' ? 'Add the charts' :
        next === 'review' ? 'Say save, or tap save' :
        (voiceLabel() + ' · tap to talk, or type');
    }
    syncComposer();
  }

  function markVoice(id) {
    var next = VOICE_PRESETS[id] ? id : 'marin';
    if (next !== voiceId) {
      audioCache = {};
      voiceWarmOk = true;
      voiceId = next;
      warmVoice();
    } else {
      voiceId = next;
    }
    try { localStorage.setItem('tv-vj-voice', voiceId); } catch (e) {}
    var buttons = document.querySelectorAll('.tv-vj-voice');
    for (var i = 0; i < buttons.length; i++) {
      var on = buttons[i].getAttribute('data-voice') === voiceId;
      buttons[i].classList.toggle('is-on', on);
      buttons[i].setAttribute('aria-checked', on ? 'true' : 'false');
    }
    if (state === 'idle' && statusEl) statusEl.textContent = voiceLabel() + ' · tap to talk, or type';
  }

  function pickBrowserVoice(preset) {
    if (!window.speechSynthesis || !preset) return null;
    var voices = window.speechSynthesis.getVoices() || [];
    var best = null;
    var bestScore = 0;
    for (var j = 0; j < voices.length; j++) {
      var v = voices[j];
      var name = (v.name || '').toLowerCase();
      var lang = (v.lang || '').toLowerCase();
      if (!name || JOKE_VOICES.test(name)) continue;
      if (lang && lang.indexOf('en') !== 0) continue;
      var score = 1;
      if (/premium|enhanced|natural/.test(name)) score += 30;
      var names = preset.names || [];
      for (var i = 0; i < names.length; i++) {
        if (name.indexOf(names[i]) !== -1) score += 24 - i * 3;
      }
      if (lang.indexOf('en-za') === 0 || lang.indexOf('en-gb') === 0) score += 2;
      if (score > bestScore) {
        bestScore = score;
        best = v;
      }
    }
    return best;
  }

  function forBrowser(line) {
    return String(line || '').replace(/\s*[—–]\s*/g, ', ').replace(/\s{2,}/g, ' ').trim();
  }

  function syncComposer() {
    var busy = committing || state === 'thinking' || state === 'speaking';
    if (typeSend) typeSend.disabled = busy;
    if (typeInput) typeInput.disabled = busy && state !== 'review';
  }

  function looksLikeSaveConfirm(text) {
    var t = String(text || '').toLowerCase().replace(/\s+/g, ' ').trim();
    if (!t) return false;
    if (/\b(change|fix|wrong|edit|update|wait|actually|meant)\b/.test(t)) return false;
    return /\b(save(?: it)?|log(?: it)?|looks good|that'?s (?:it|right|correct)|confirm|submit|go ahead|yes(?: please)?|yep|yeah|perfect)\b/.test(t);
  }

  function savedMarkOn() {
    try { return sessionStorage.getItem(storageKey + '-saved') === '1'; } catch (e) { return false; }
  }

  function markJournalSaved() {
    journalSaved = true;
    try {
      sessionStorage.setItem(storageKey + '-saved', '1');
      sessionStorage.removeItem(storageKey);
    } catch (e) {}
  }

  function persistDraft() {
    try {
      if (journalSaved || savedMarkOn()) {
        sessionStorage.removeItem(storageKey);
        return;
      }
      if (!draft || (!draft.symbol && draft.entry_price == null && history.length < 1)) {
        sessionStorage.removeItem(storageKey);
        return;
      }
      sessionStorage.setItem(storageKey, JSON.stringify({
        draft: draft,
        history: history.slice(-16),
        transcriptDump: transcriptDump.slice(-24),
        hasBefore: hasBefore,
        hasAfter: hasAfter,
        skipShot: skipShot,
        state: state === 'review' ? 'review' : 'active'
      }));
    } catch (e) {}
  }

  function clearPersisted() {
    try { sessionStorage.removeItem(storageKey); } catch (e) {}
  }

  function showNewTrade(on) {
    var btn = document.getElementById('tv-vj-new');
    if (btn) btn.classList.toggle('d-none', !on);
  }

  function startFresh() {
    journalSaved = false;
    try { sessionStorage.removeItem(storageKey + '-saved'); } catch (e) {}
    draft = {};
    history = [];
    transcriptDump = [];
    hasBefore = false;
    hasAfter = false;
    hasShot = false;
    skipShot = false;
    reviewMode = false;
    fixField = '';
    clearPersisted();
    [
      'symbol', 'instrument_id', 'entry_price', 'stop_loss', 'take_profit', 'exit_price',
      'lot_size', 'session_type', 'strategy', 'timeframe', 'confidence_level',
      'pre_trade_plan', 'post_trade_notes', 'lessons_learned', 'emotion',
      'guide_why', 'guide_voice_dump', 'guide_feeling_before', 'guide_feeling_after',
      'guide_followed_plan', 'guide_what_happened', 'guide_reflection', 'guide_emotions',
      'guide_setup_tags', 'guide_session', 'guide_moved_sl', 'guide_early_close',
      'guide_partials', 'guide_added', 'guide_mgmt_note'
    ].forEach(function (id) { setVal(id, ''); });
    confirming = false;
    if (stage) {
      stage.classList.remove('is-confirm');
      stage.classList.remove('is-review');
      stage.classList.remove('is-slip');
    }
    renderChips({}, {});
    renderPrompts('');
    if (shotEl) shotEl.classList.add('d-none');
    if (journalEl) journalEl.classList.add('d-none');
    if (summaryEl) summaryEl.innerHTML = '';
    setLive('');
    setAi('Tell me the trade.');
    setPhase('facts');
    setState('idle');
    showNewTrade(false);
    showRedo(false);
    undoStack = null;
    var check = document.getElementById('tv-vj-check');
    if (check) check.classList.add('d-none');
    ['tv-vj-shot-before', 'tv-vj-shot-after'].forEach(function (id) {
      var slot = document.getElementById(id);
      if (!slot) return;
      slot.classList.remove('has-file');
      var img = slot.querySelector('img');
      if (img) img.remove();
    });
    var doneBtn = document.getElementById('tv-vj-shot-done');
    if (doneBtn) doneBtn.classList.add('d-none');
  }

  function seedFromBoot() {
    if (boot.complete && typeof boot.complete === 'object') {
      var c = boot.complete;
      draft = {
        symbol: c.symbol || null,
        instrument_id: c.instrument_id || null,
        trade_type: c.trade_type || null,
        entry_price: c.entry_price != null ? Number(c.entry_price) : null,
        stop_loss: c.stop_loss != null ? Number(c.stop_loss) : null,
        take_profit: c.take_profit != null ? Number(c.take_profit) : null,
        exit_price: c.exit_price != null ? Number(c.exit_price) : null,
        lot_size: c.lot_size != null ? Number(c.lot_size) : null,
        session_type: c.session_type || null,
        strategy: c.strategy || null,
        status: c.status === 'CLOSED' ? 'closed' : (c.status === 'OPEN' ? 'open' : null),
        thesis_notes: c.pre_trade_plan || null,
        voice_dump: c.post_trade_notes || c.pre_trade_plan || null,
        setup_tags: [],
        emotions: []
      };
      renderChips(draft, {});
      return;
    }
    try {
      if (savedMarkOn()) {
        sessionStorage.removeItem(storageKey);
        sessionStorage.removeItem(storageKey + '-saved');
        return;
      }
      var raw = sessionStorage.getItem(storageKey);
      if (!raw) return;
      var saved = JSON.parse(raw);
      if (!saved || !saved.draft) return;
      draft = saved.draft || {};
      history = Array.isArray(saved.history) ? saved.history : [];
      transcriptDump = Array.isArray(saved.transcriptDump) ? saved.transcriptDump : [];
      hasBefore = !!saved.hasBefore;
      hasAfter = !!saved.hasAfter;
      skipShot = !!saved.skipShot;
      hasShot = hasBefore || hasAfter;
      renderChips(draft, {});
      if (aiEl && history.length) {
        var lastAsst = '';
        for (var i = history.length - 1; i >= 0; i--) {
          if (history[i] && history[i].role === 'assistant') {
            lastAsst = history[i].content || '';
            break;
          }
        }
        if (lastAsst) setAi(lastAsst);
      }
    } catch (e) {}
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

  function plainWords(text) {
    return String(text || '')
      .replace(/\s*[—–]\s*/g, ', ')
      .replace(/\s+-\s+/g, ', ')
      .replace(/\s{2,}/g, ' ')
      .replace(/\s+,/g, ',')
      .trim();
  }

  function setAi(text) {
    lastReply = plainWords(text);
    if (aiEl) {
      aiEl.textContent = lastReply;
      aiEl.classList.add('is-in');
    }
  }

  function setLive(text) {
    if (!liveEl) return;
    var shown = plainWords(text);
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

  function clearBargeIn() {
    clearInterval(rec.bargeWatch);
    rec.bargeWatch = null;
    rec.bargeHits = 0;
  }

  function armBargeIn() {
    clearBargeIn();
    rec.bargeFired = false;
    rec.bargeArmedAt = Date.now() + 480;
    rec.bargeHits = 0;
    if (!rec.analyser) return;
    var data = new Uint8Array(rec.analyser.fftSize);
    rec.bargeWatch = setInterval(function () {
      if (state !== 'speaking' || rec.bargeFired) {
        clearBargeIn();
        return;
      }
      rec.analyser.getByteTimeDomainData(data);
      var sum = 0;
      for (var i = 0; i < data.length; i++) {
        var v = (data[i] - 128) / 128;
        sum += v * v;
      }
      var rms = Math.sqrt(sum / data.length);
      if (Date.now() < rec.bargeArmedAt) return;
      if (rms > 0.1) rec.bargeHits += 1;
      else rec.bargeHits = 0;
      if (rec.bargeHits >= 3) {
        rec.bargeFired = true;
        clearBargeIn();
        try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) {}
        var a = document.getElementById('tv-vj-tts');
        if (a) {
          try { a.pause(); } catch (e2) {}
          a.remove();
        }
        startRec();
      }
    }, 80);
  }

  function stopTTS() {
    clearBargeIn();
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) {}
    var a = document.getElementById('tv-vj-tts');
    if (a) {
      try { a.pause(); } catch (e) {}
      a.remove();
    }
  }

  var SPEAK_AHEAD = [
    'Okay.',
    'Alright.',
    'Yeah, I got that.',
    'Okay, okay.',
    'Right.',
    'Does that look right?',
    'Which part should I change?',
    'What price did you enter at?',
    'What was your stop loss?',
    'What was your take profit?',
    'Where did you get out?',
    'Why did you enter?',
    'Did you follow your rules on this one?',
    'How were you feeling while you were in it?',
    'And how do you feel about it now?',
    'How confident were you, one to ten?',
    'What did this one teach you?',
    'What are you going to do differently next time?',
    'How did you manage the trade?',
    'If you could fix one thing about this trade, what would it be?',
    'Add the before and after, if you have them.',
    'You still in it, or are you out?'
  ];

  function voiceKey(line) {
    return voiceId + '|h5|' + line;
  }

  function neuralSpeak() {
    return !!(boot.speakEnabled && boot.speakUrl && voiceWarmOk);
  }

  function noteSpeakFailed(status) {
    if (status === 403 || status === 503) {
      boot.speakEnabled = false;
      voiceWarmOk = false;
    }
  }

  function cachedAudio(line) {
    var hit = audioCache[voiceKey(line)];
    return hit && hit !== 'loading' ? hit : '';
  }

  function prefetchSpeak(line) {
    if (!neuralSpeak() || !line) return;
    var key = voiceKey(line);
    if (audioCache[key]) return;
    audioCache[key] = 'loading';
    fetch(boot.speakUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify({ text: line, voice: voiceId })
    }).then(function (r) {
      if (!r.ok) {
        noteSpeakFailed(r.status);
        delete audioCache[key];
        return null;
      }
      return r.blob();
    }).then(function (blob) {
      if (!blob) return;
      audioCache[key] = URL.createObjectURL(blob);
    }).catch(function () {
      delete audioCache[key];
    });
  }

  function warmVoice() {
    if (!neuralSpeak()) return;
    var i = 0;
    function next() {
      if (!voiceWarmOk || i >= SPEAK_AHEAD.length) return;
      prefetchSpeak(SPEAK_AHEAD[i]);
      i += 1;
      setTimeout(next, 280);
    }
    setTimeout(next, 500);
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
    armBargeIn();
    var wrapped = function () {
      clearBargeIn();
      if (rec.bargeFired) return;
      setTimeout(function () { if (typeof then === 'function') then(); }, 520);
    };
    var done = wrapped;

    function browserSpeak() {
      function go() {
        if (!window.speechSynthesis) { done(); return; }
        try {
          var preset = VOICE_PRESETS[voiceId] || VOICE_PRESETS.marin;
          var chosen = pickBrowserVoice(preset);
          var u = new SpeechSynthesisUtterance(forBrowser(line));
          u.lang = (chosen && chosen.lang) || 'en-GB';
          u.rate = preset.rate;
          u.pitch = preset.pitch;
          if (chosen) {
            u.voice = chosen;
            u.lang = chosen.lang || u.lang;
          }
          u.onend = done;
          u.onerror = done;
          window.speechSynthesis.speak(u);
        } catch (e) {
          done();
        }
      }
      if (window.speechSynthesis && !(window.speechSynthesis.getVoices() || []).length) {
        var fired = false;
        var run = function () { if (fired) return; fired = true; go(); };
        window.speechSynthesis.addEventListener('voiceschanged', run, { once: true });
        setTimeout(run, 400);
        return;
      }
      go();
    }

    if (!neuralSpeak()) {
      browserSpeak();
      return;
    }

    function playUrl(url, after) {
      var prev = document.getElementById('tv-vj-tts');
      if (prev) prev.remove();
      var audio = document.createElement('audio');
      audio.id = 'tv-vj-tts';
      audio.src = url;
      audio.addEventListener('ended', after, { once: true });
      audio.addEventListener('error', function () { browserSpeak(); }, { once: true });
      document.body.appendChild(audio);
      var play = audio.play();
      if (play && play.catch) play.catch(function () { browserSpeak(); });
    }

    var exact = cachedAudio(line);
    if (exact) {
      playUrl(exact, done);
      return;
    }
    fetch(boot.speakUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify({ text: line, voice: voiceId })
    }).then(function (r) {
      if (!r.ok) {
        noteSpeakFailed(r.status);
        throw new Error('tts');
      }
      return r.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      audioCache[voiceKey(line)] = url;
      playUrl(url, done);
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

  function setVoiceVisual(on, rms) {
    rec.voiceOn = !!on;
    rec.voiceRms = rms || 0;
    var live = rec.voiceOn && (state === 'listening' || rec.recording);
    if (stage) stage.classList.toggle('is-voice', live);
    var page = document.querySelector('.tv-vj-page');
    if (page) page.classList.toggle('is-voice', live);
  }

  function sizeWater() {
    var water = document.getElementById('tv-vj-water');
    if (!water || !water.getContext) return null;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = window.innerWidth || 1;
    var h = window.innerHeight || 1;
    if (water.width !== Math.floor(w * dpr) || water.height !== Math.floor(h * dpr)) {
      water.width = Math.floor(w * dpr);
      water.height = Math.floor(h * dpr);
      water.style.width = w + 'px';
      water.style.height = h + 'px';
    }
    return water;
  }

  function drawWater() {
    var water = sizeWater();
    if (!water) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var ctx = water.getContext('2d');
    var w = water.width / dpr;
    var h = water.height / dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    var speaking = rec.voiceOn && (state === 'listening' || rec.recording);
    var gold = '#e6c45a';
    var corners = [
      { x: 0, y: 0 },
      { x: w, y: 0 },
      { x: 0, y: h },
      { x: w, y: h }
    ];
    // Soft corner wells always present; bloom brighter while speaking.
    corners.forEach(function (c, idx) {
      var pulse = speaking ? (0.14 + rec.voiceRms * 0.7 + Math.sin(Date.now() / 380 + idx) * 0.05) : 0.05;
      var rad = speaking ? (160 + rec.voiceRms * 280) : 120;
      var g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, rad);
      g.addColorStop(0, rgbOf(gold, pulse));
      g.addColorStop(0.45, rgbOf(gold, pulse * 0.38));
      g.addColorStop(1, rgbOf(gold, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(c.x, c.y, rad, 0, Math.PI * 2);
      ctx.fill();
    });
    if (speaking && Date.now() - rec.rippleAt > 70) {
      rec.rippleAt = Date.now();
      var cx = w / 2;
      var cy = Math.min(h * 0.28, 190);
      // Center motes — denser while voice is loud
      var bursts = 1 + Math.floor(rec.voiceRms * 3);
      for (var b = 0; b < bursts; b++) {
        rec.waterRipples.push({
          x: cx + (Math.random() - 0.5) * (50 + rec.voiceRms * 80),
          y: cy + (Math.random() - 0.5) * (36 + rec.voiceRms * 40),
          r: 4 + Math.random() * 10,
          a: 0.22 + rec.voiceRms * 0.6,
          grow: 0.85 + rec.voiceRms * 2.6,
          kind: 'mote'
        });
      }
      // Corner ink blooms
      corners.forEach(function (c) {
        if (Math.random() > 0.4 - rec.voiceRms * 0.25) return;
        rec.waterRipples.push({
          x: c.x + (c.x === 0 ? 28 : -28) + (Math.random() - 0.5) * 22,
          y: c.y + (c.y === 0 ? 28 : -28) + (Math.random() - 0.5) * 22,
          r: 12 + Math.random() * 20 + rec.voiceRms * 18,
          a: 0.26 + rec.voiceRms * 0.55,
          grow: 1.3 + rec.voiceRms * 3.8,
          kind: 'corner'
        });
      });
      if (rec.waterRipples.length > 48) rec.waterRipples.splice(0, rec.waterRipples.length - 48);
    }
    for (var i = rec.waterRipples.length - 1; i >= 0; i--) {
      var p = rec.waterRipples[i];
      p.r += p.grow;
      p.a *= p.kind === 'corner' ? 0.952 : 0.96;
      if (p.a < 0.02 || p.r > (p.kind === 'corner' ? 220 : 130)) {
        rec.waterRipples.splice(i, 1);
        continue;
      }
      if (p.kind === 'corner') {
        ctx.beginPath();
        ctx.strokeStyle = rgbOf(gold, p.a);
        ctx.lineWidth = 1.4;
        ctx.ellipse(p.x, p.y, p.r, p.r * 0.72, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.fillStyle = rgbOf(gold, p.a * 0.18);
        ctx.ellipse(p.x, p.y, p.r * 0.35, p.r * 0.28, 0, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.fillStyle = rgbOf(gold, p.a * 0.4);
        ctx.arc(p.x, p.y, Math.max(1.2, p.r * 0.18), 0, Math.PI * 2);
        ctx.fill();
      }
    }
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
    return 'rgba(230,196,90,' + a + ')';
  }

  function bloomRadius(angle, t, amp) {
    var base = 72 + amp * 30;
    var n =
      Math.sin(angle * 2.2 + t * 0.75) * (18 + amp * 10) +
      Math.cos(angle * 3.7 - t * 1.05) * (14 + amp * 9) +
      Math.sin(angle * 5.4 + t * 1.35) * (11 + amp * 8) +
      Math.cos(angle * 8.1 - t * 0.9) * (7 + amp * 6) +
      Math.sin(angle * 11 + t * 1.9) * (4.5 + amp * 4) +
      Math.sin(angle * 1.15 + t * 0.4) * (9 + amp * 5);
    return Math.max(42, base + n);
  }

  function drawOrb() {
    rec.raf = requestAnimationFrame(drawOrb);
    drawWater();
    if (!canvas || !canvas.getContext) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var css = 320;
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

    var listening = state === 'listening' || rec.recording;
    var voice = listening && rec.voiceOn;
    var amp = 0.1;
    if (voice && rec.voiceRms) {
      amp = Math.min(1, 0.18 + rec.voiceRms * 4.2);
    } else if (state === 'speaking') {
      amp = 0.32 + Math.sin(Date.now() / 170) * 0.1;
    } else if (state === 'thinking') {
      amp = 0.18 + Math.sin(Date.now() / 420) * 0.07;
    } else {
      amp = 0.1 + Math.sin(Date.now() / 1600) * 0.035;
    }
    rec.amp = rec.amp * 0.78 + amp * 0.22;

    var t = Date.now() / 1000;
    var gold = '#e6c45a';
    var goldSoft = '#f3dfa0';
    var goldDeep = '#b8922e';

    var glow = ctx.createRadialGradient(cx, cy, 10, cx, cy, 150 + rec.amp * 40);
    glow.addColorStop(0, rgbOf(goldSoft, voice ? 0.42 + rec.amp * 0.35 : 0.22));
    glow.addColorStop(0.4, rgbOf(gold, voice ? 0.18 + rec.amp * 0.14 : 0.1));
    glow.addColorStop(1, rgbOf(gold, 0));
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);

    function pathBloom(scale, stretchY) {
      var steps = 96;
      stretchY = stretchY == null ? 0.88 : stretchY;
      ctx.beginPath();
      for (var i = 0; i <= steps; i++) {
        var ang = (i / steps) * Math.PI * 2;
        var r = bloomRadius(ang, t, rec.amp) * scale;
        var x = cx + Math.cos(ang) * r;
        var y = cy + Math.sin(ang) * r * stretchY;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
    }

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Math.sin(t * 0.28) * 0.08 + Math.cos(t * 0.17) * 0.04);
    ctx.scale(1 + Math.sin(t * 0.5) * 0.02, 1 + Math.cos(t * 0.4) * 0.025);
    ctx.translate(-cx, -cy);

    ctx.filter = 'blur(10px)';
    pathBloom(1.12, 0.9);
    ctx.fillStyle = rgbOf(gold, 0.22 + rec.amp * 0.12);
    ctx.fill();
    ctx.filter = 'none';

    pathBloom(1, 0.86);
    var body = ctx.createRadialGradient(cx - 22, cy - 28, 6, cx + 8, cy + 10, 118);
    body.addColorStop(0, '#fff6d4');
    body.addColorStop(0.22, goldSoft);
    body.addColorStop(0.48, gold);
    body.addColorStop(0.78, goldDeep);
    body.addColorStop(1, '#5c4718');
    ctx.fillStyle = body;
    ctx.fill();

    // Soft facet highlights — crumpled leaf feel
    ctx.globalCompositeOperation = 'lighter';
    pathBloom(0.7, 0.84);
    var facet = ctx.createRadialGradient(cx - 26, cy - 30, 2, cx - 8, cy - 6, 54);
    facet.addColorStop(0, 'rgba(255,252,235,0.55)');
    facet.addColorStop(0.55, rgbOf(goldSoft, 0.18));
    facet.addColorStop(1, 'rgba(230,196,90,0)');
    ctx.fillStyle = facet;
    ctx.fill();
    ctx.globalCompositeOperation = 'source-over';

    pathBloom(0.48, 0.82);
    var core = ctx.createRadialGradient(cx - 12, cy - 16, 1, cx, cy, 46);
    core.addColorStop(0, 'rgba(255,250,230,0.9)');
    core.addColorStop(0.5, rgbOf(goldSoft, 0.35));
    core.addColorStop(1, rgbOf(gold, 0));
    ctx.fillStyle = core;
    ctx.fill();
    ctx.restore();

    if (voice && Date.now() - (rec.orbRippleAt || 0) > 200) {
      rec.orbRippleAt = Date.now();
      rec.ripples.push({ r: 68, a: 0.26 + rec.amp * 0.25, rot: Math.random() * Math.PI });
      if (rec.ripples.length > 6) rec.ripples.shift();
    }
    for (var r = rec.ripples.length - 1; r >= 0; r--) {
      var ring = rec.ripples[r];
      ring.r += 1.4 + rec.amp * 1.8;
      ring.a *= 0.94;
      if (ring.a < 0.03 || ring.r > 150) {
        rec.ripples.splice(r, 1);
        continue;
      }
      ctx.beginPath();
      for (var j = 0; j <= 56; j++) {
        var a2 = (j / 56) * Math.PI * 2 + (ring.rot || 0);
        var rr = ring.r + Math.sin(a2 * 5 + t * 2) * 7;
        var x2 = cx + Math.cos(a2) * rr;
        var y2 = cy + Math.sin(a2) * rr * 0.88;
        if (j === 0) ctx.moveTo(x2, y2);
        else ctx.lineTo(x2, y2);
      }
      ctx.closePath();
      ctx.strokeStyle = rgbOf(gold, ring.a);
      ctx.lineWidth = 1.4;
      ctx.stroke();
    }
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
      if (rms > 0.038) {
        heard = true;
        quiet = 0;
        setVoiceVisual(true, rms);
      } else {
        quiet += 100;
        if (quiet >= 180) setVoiceVisual(false, rms);
      }
      var sinceWords = Date.now() - (rec.lastHeardAt || 0);
      if (heard && quiet >= 4200 && sinceWords > 900) stopRec(false);
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
      rec.sr.lang = 'en-GB';
      rec.sr.maxAlternatives = 3;
      rec.base = rec.text || '';
      rec.sr.onresult = function (ev) {
        var finals = [];
        var interim = '';
        for (var i = 0; i < ev.results.length; i++) {
          var best = '';
          var bestScore = -1;
          var bestFit = -1;
          for (var a = 0; a < ev.results[i].length; a++) {
            var alt = ev.results[i][a];
            if (!alt) continue;
            var said = alt.transcript || '';
            var score = typeof alt.confidence === 'number' ? alt.confidence : 0;
            var fit = fidelity(said);
            if (!best || score > bestScore + 0.05 || (Math.abs(score - bestScore) <= 0.05 && fit > bestFit)) {
              best = said;
              bestScore = score;
              bestFit = fit;
            }
          }
          if (ev.results[i].isFinal) finals.push(best);
          else interim += best;
        }
        var sessionText = finals.join(' ').replace(/\s+/g, ' ').trim();
        rec.text = (rec.base + ' ' + sessionText).replace(/\s+/g, ' ').trim();
        var shown = (rec.text + (interim ? ' ' + interim : '')).replace(/\s+/g, ' ').trim();
        rec.live = shown;
        noteHeard(shown);
        rec.lastHeardAt = Date.now();
        setLive(rec.faithful && fidelity(rec.faithful) > fidelity(shown) ? rec.faithful : shown);
        if (shown) {
          clearTimeout(rec.silence);
          var words = shown.split(/\s+/).length;
          var settled = /[.?!]\s*$/.test(shown) || (/\d\s*$/.test(shown) && words >= 6);
          rec.silence = setTimeout(function () {
            if (rec.recording) stopRec(false);
          }, settled ? 1600 : 3200);
        }
      };
      rec.sr.onerror = function (ev) {
        var code = ev && ev.error;
        if (code === 'not-allowed' || code === 'service-not-allowed') {
          rec.srBlocked = true;
          showErr('Speech recognition is blocked. Keep talking and we’ll use the recording, or type below.');
        }
      };
      rec.sr.onend = function () {
        if (rec.recording && rec.sr && !rec.srBlocked) {
          rec.base = rec.live || rec.text || '';
          try { rec.sr.start(); } catch (e) {}
        }
      };
      rec.sr.start();
      return true;
    } catch (e) {
      return false;
    }
  }

  function startRec() {
    if (rec.recording || committing) return;
    if (state === 'thinking') return;
    rec.text = '';
    rec.live = '';
    rec.base = '';
    rec.faithful = '';
    rec.lastHeardAt = 0;
    rec.chunks = [];
    rec.gen += 1;
    setVoiceVisual(false, 0);
    var gen = rec.gen;
    setLive('');
    showErr('');
    ensureStream().then(function (stream) {
      if (gen !== rec.gen) return;
      attachAnalyser(stream);
      rec.mime = pickMime();
      try {
        var recOpts = rec.mime ? { mimeType: rec.mime, audioBitsPerSecond: 128000 } : { audioBitsPerSecond: 128000 };
        rec.mr = new MediaRecorder(stream, recOpts);
      } catch (e) {
        try { rec.mr = rec.mime ? new MediaRecorder(stream, { mimeType: rec.mime }) : new MediaRecorder(stream); }
        catch (e2) { rec.mr = new MediaRecorder(stream); }
      }
      rec.mr.ondataavailable = function (e) {
        if (e.data && e.data.size) rec.chunks.push(e.data);
      };
      try { rec.mr.start(250); } catch (e) { rec.mr.start(); }
      startSpeech();
      rec.recording = true;
      setState('listening');
      watchLoudness();
      clearTimeout(rec.maxTimer);
      rec.maxTimer = setTimeout(function () {
        if (rec.recording) stopRec(false);
      }, reviewMode ? 12000 : 25000);
    }).catch(function () {
      showErr(window.isSecureContext
        ? 'Allow the microphone, then tap again — or type below.'
        : 'Voice needs HTTPS — you can still type below.');
      if (state !== 'review') setState('idle');
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
    setVoiceVisual(false, 0);
    var gen = rec.gen;
    var box = { blob: null, recDone: false, srDone: false, silent: !!silent };

    function go() {
      if (gen !== rec.gen) return;
      if (!box.recDone || !box.srDone) return;
      if (box.silent) return;
      finishUtterance(String(rec.live || rec.text || '').trim(), box.blob);
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

  function fidelity(text) {
    var t = String(text || '');
    var digits = (t.match(/\d/g) || []).length;
    var words = t.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/).filter(Boolean).length;
    return digits * 8 + words;
  }

  function noteHeard(text) {
    var t = String(text || '').trim();
    if (!t) return;
    if (fidelity(t) >= fidelity(rec.faithful || '')) rec.faithful = t;
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

  function captionIsEnough(text) {
    var t = String(text || '').trim();
    if (!t || /^(um+|uh+|hmm+|er+|ah+)$/i.test(t)) return false;
    if (/\d/.test(t)) return true;
    if (tokensOf(t).length >= 2) return true;
    return /^(gold|silver|euro|cable|nasdaq|dow|dax|ftse|bitcoin|btc|eth|long|short|buy|sell|yes|no|save|open|closed)$/i.test(t);
  }

  var WHISPER_JUNK = /^(thanks for watching\.?|thank you(?: for watching)?\.?|subscribe\.?|you\.?|bye\.?|music\.?|applause\.?|[.\s]+)$/i;

  function pickTranscript(whisper, local) {
    whisper = String(whisper || '').trim();
    local = String(local || '').trim();
    if (isPromptLeak(whisper) || WHISPER_JUNK.test(whisper)) whisper = '';
    if (looksLikeEcho(whisper)) whisper = '';
    if (looksLikeEcho(local)) local = '';
    // A tiny transcript against a real sentence is usually a bad guess.
    if (whisper && local) {
      var wt = tokensOf(whisper);
      var lt = tokensOf(local);
      if (wt.length <= 2 && lt.length >= 5 && tokenOverlap(whisper, local) < 0.34) return local;
      // A transcript that swaps the sentence is not what they said.
      if (tokenOverlap(whisper, local) < 0.45 && fidelity(local) >= fidelity(whisper)) return local;
      if (fidelity(local) > fidelity(whisper) + 6) return local;
    }
    if (whisper) return whisper;
    return local;
  }

  function heardNothing() {
    setLive('');
    if (reviewMode) {
      startRec();
      return;
    }
    setState('idle');
    if (statusEl) statusEl.textContent = 'Didn’t catch that — tap again, or type';
  }

  function finishUtterance(srText, blob) {
    var local = String(srText || '').trim();
    var faithful = String(rec.faithful || '').trim();
    if (looksLikeEcho(local)) local = '';
    if (looksLikeEcho(faithful)) faithful = '';
    if (faithful && (!local || (tokenOverlap(faithful, local) < 0.72 && fidelity(faithful) > fidelity(local)))) {
      local = faithful;
    }
    var blobOk = !!(blob && blob.size > 250 && boot.transcribeEnabled);
    if (blobOk) {
      committing = true;
      setState('thinking');
      setLive(local || '…');
      var fd = new FormData();
      fd.append('audio', blob, blobName(blob.type || rec.mime));
      if (local) fd.append('hint', local.slice(0, 240));
      fetch(boot.transcribeUrl || '/api/voice/transcribe', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf() },
        body: fd
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          committing = false;
          var whispered = res && res.ok && res.d && res.d.text ? String(res.d.text).trim() : '';
          var text = pickTranscript(whispered, local);
          if (text) {
            setLive(text);
            sendTurn(text);
          } else heardNothing();
        })
        .catch(function () {
          committing = false;
          if (local) sendTurn(local);
          else heardNothing();
        });
      return;
    }
    if (local && local.replace(/\s/g, '').length >= 2) {
      setLive(local);
      sendTurn(local);
      return;
    }
    heardNothing();
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

  function renderChips(d, m) {
    var el = document.getElementById('tv-vj-chips');
    if (!el) return;
    d = d || draft;
    m = m || lastMetrics || {};
    lastMetrics = m;
    var chips = [];
    if (d.symbol) chips.push({ t: d.symbol, k: '', f: 'symbol' });
    if (d.trade_type) chips.push({ t: d.trade_type === 'SELL' ? 'Short' : 'Long', k: '', f: 'trade_type' });
    if (d.entry_price != null) chips.push({ t: 'In ' + d.entry_price, k: '', f: 'entry_price' });
    if (d.stop_loss != null) chips.push({ t: 'SL ' + d.stop_loss, k: '', f: 'stop_loss' });
    if (d.take_profit != null) chips.push({ t: 'TP ' + d.take_profit, k: '', f: 'take_profit' });
    if (d.status === 'closed' && d.exit_price != null) chips.push({ t: 'Out ' + d.exit_price, k: '', f: 'exit_price' });
    if (m.rr_label) chips.push({ t: m.rr_label, k: 'is-rr', f: '' });
    if (m.profit_loss != null) {
      var pnl = Number(m.profit_loss);
      chips.push({ t: (pnl >= 0 ? '+' : '') + pnl, k: pnl >= 0 ? 'is-win' : 'is-loss', f: '' });
    }
    if (d.session_type) chips.push({ t: String(d.session_type).replace(' Session', '').replace(' Sessions', ''), k: d.session_assumed ? 'is-soft' : '', f: 'session_type' });
    if (d.timeframe && d.timeframe !== 'unspecified') chips.push({ t: d.timeframe, k: '', f: 'timeframe' });
    if (d.lot_size != null && (Number(d.lot_size) !== 1 || d.lot_assumed)) {
      chips.push({ t: d.lot_size + ' lot', k: d.lot_assumed ? 'is-soft' : '', f: 'lot_size' });
    }
    if (d.confidence_level != null && d.confidence_level !== '') chips.push({ t: d.confidence_level + '/10', k: '', f: 'confidence_level' });
    if (d.thesis_notes && d.thesis_notes !== 'skipped') {
      var why = String(d.thesis_notes);
      chips.push({ t: why.length > 28 ? (why.slice(0, 26) + '…') : why, k: 'is-why', f: '' });
    }
    el.innerHTML = chips.map(function (c) {
      var tap = c.f ? ' is-tap' : '';
      if (confirming && c.f) tap += ' is-live';
      var attr = c.f ? ' data-fix="' + esc(c.f) + '" role="button" tabindex="0"' : '';
      return '<span class="tv-vj-chip ' + c.k + tap + '"' + attr + '>' + esc(c.t) + '</span>';
    }).join('');
    el.classList.toggle('is-on', chips.length > 0);
    if (chipHint) chipHint.classList.toggle('d-none', chips.filter(function (c) { return c.f; }).length < 1);
    showNewTrade(!!(d && d.symbol));
    renderSlip(d, m);
  }

  function cleanNote(v) {
    v = v == null ? '' : String(v).trim();
    if (!v || v === 'skipped') return '';
    return v;
  }

  function journalSections(d) {
    d = d || {};
    var rules = '';
    if (d.followed_plan === 'yes') rules = 'You followed your rules.';
    else if (d.followed_plan === 'mostly') rules = 'Mostly on the rules.';
    else if (d.followed_plan === 'no') rules = 'You broke your rules on this one.';
    var mistake = cleanNote(d.mistake);
    if (mistake === 'none') mistake = 'Nothing you’d change.';
    var sections = [];
    function add(label, text) {
      text = cleanNote(text);
      if (text) sections.push({ label: label, text: text });
    }
    add('Why', d.thesis_notes);
    if (rules) sections.push({ label: 'Rules', text: rules });
    add('In the trade', d.feeling_during);
    add('Now', d.feeling_after);
    add('How you managed it', d.managed_note);
    if (mistake) sections.push({ label: 'The one thing', text: mistake });
    add('What it taught you', d.lessons);
    add('Next time', d.improve_next);
    return sections;
  }

  function renderSlip(d, m) {
    var el = document.getElementById('tv-vj-slip');
    if (!el) return;
    d = d || {};
    m = m || {};
    if (reviewMode || !d.symbol) {
      el.classList.add('d-none');
      el.innerHTML = '';
      if (stage) stage.classList.remove('is-slip');
      return;
    }
    function tap(label, field) {
      return '<button type="button" class="tv-vj-slip-level" data-fix="' + esc(field) + '">' + esc(label) + '</button>';
    }
    var side = d.trade_type === 'SELL' ? 'Short' : (d.trade_type ? 'Long' : '');
    var names = [];
    if (side) names.push('<button type="button" class="tv-vj-slip-name" data-fix="trade_type">' + esc(side) + '</button>');
    names.push('<button type="button" class="tv-vj-slip-name" data-fix="symbol">' + esc(d.symbol) + '</button>');
    var levels = [];
    if (d.entry_price != null) levels.push(tap('In ' + d.entry_price, 'entry_price'));
    if (d.stop_loss != null) levels.push(tap('Stop ' + d.stop_loss, 'stop_loss'));
    if (d.take_profit != null) levels.push(tap('Target ' + d.take_profit, 'take_profit'));
    if (d.status === 'closed' && d.exit_price != null) levels.push(tap('Out ' + d.exit_price, 'exit_price'));
    var picks = [];
    if (m.rr_label) picks.push('<span class="tv-vj-slip-level is-quiet">' + esc(m.rr_label) + '</span>');
    if (d.session_type) picks.push(tap(String(d.session_type).replace(' Session', '').replace(' Sessions', ''), 'session_type'));
    if (d.entry_time && d.entry_time !== 'unspecified') picks.push('<span class="tv-vj-slip-level is-quiet">' + esc(d.entry_time) + '</span>');
    if (d.timeframe && d.timeframe !== 'unspecified') picks.push(tap(d.timeframe, 'timeframe'));
    if (d.lot_size != null) picks.push(tap(d.lot_size + ' lot', 'lot_size'));
    if (d.confidence_level != null && d.confidence_level !== '') picks.push(tap(d.confidence_level + '/10', 'confidence_level'));
    var stateLine = d.status === 'closed' ? 'Closed' : (d.status === 'open' ? 'Still in it' : '');
    var sections = journalSections(d).map(function (s) {
      var text = s.text;
      if (text.length > 280) text = text.slice(0, 278) + '…';
      return '<div class="tv-vj-slip-block"><p class="tv-vj-slip-label">' + esc(s.label) + '</p>' +
        '<p class="tv-vj-slip-text">' + esc(text) + '</p></div>';
    }).join('');
    el.innerHTML =
      '<div class="tv-vj-slip-head"><div class="tv-vj-slip-id">' + names.join('<span class="tv-vj-slip-dot">·</span>') + '</div>' +
      (stateLine ? '<p class="tv-vj-slip-state">' + esc(stateLine) + '</p>' : '') + '</div>' +
      (levels.length ? '<div class="tv-vj-slip-levels">' + levels.join('') + '</div>' : '') +
      (picks.length ? '<div class="tv-vj-slip-picks">' + picks.join('') + '</div>' : '') +
      sections +
      (confirming ? '<p class="tv-vj-slip-foot">Tap a figure if it’s wrong</p>' : '');
    el.classList.toggle('is-confirm', !!confirming);
    el.classList.remove('d-none');
    if (stage) stage.classList.add('is-slip');
  }

  function askFix(field) {
    fixField = field || '';
    reviewMode = false;
    if (stage) stage.classList.remove('is-review');
    renderSlip(draft, lastMetrics || {});
    var prompts = {
      symbol: 'What market was it?',
      trade_type: 'Long or short?',
      entry_price: 'What price did you enter at?',
      stop_loss: 'What was your stop loss?',
      take_profit: 'What was your take profit?',
      exit_price: 'Where did you get out?',
      session_type: 'Which session?',
      lot_size: 'What size were you trading?',
      timeframe: 'What timeframe were you on?',
      confidence_level: 'Confidence from one to ten?'
    };
    var line = prompts[fixField] || 'Which part should I change?';
    if (journalEl) journalEl.classList.add('d-none');
    skipShot = true;
    speak(line, startRec);
  }

  function renderJournal(data) {
    if (!summaryEl) return;
    var d = (data && data.draft) || draft;
    var m = (data && data.metrics) || {};
    var side = d.trade_type === 'SELL' ? 'Short' : 'Long';
    var status = d.status === 'closed' ? 'Closed' : 'Open';
    var hero = '';
    if (d.status === 'closed' && m.profit_loss != null) {
      var pnl = Number(m.profit_loss);
      var cls = pnl >= 0 ? 'is-win' : 'is-loss';
      hero = '<div class="tv-vj-hero"><div class="tv-vj-hero-kicker">Result</div>' +
        '<div class="tv-vj-hero-value ' + cls + '">' + esc((pnl >= 0 ? '+' : '') + pnl) + '</div>' +
        '<div class="tv-vj-hero-sub">' + esc(m.rr_label ? ('R:R ' + m.rr_label) : (status + ' trade')) + '</div></div>';
    } else if (m.rr_label) {
      var sub = m.sl_pips != null ? ('Stop ' + m.sl_pips + ' away') : 'Planned return';
      if (m.tp_pips != null && m.sl_pips != null) sub = 'Risk ' + m.sl_pips + ' to make ' + m.tp_pips;
      hero = '<div class="tv-vj-hero"><div class="tv-vj-hero-kicker">Planned R:R</div>' +
        '<div class="tv-vj-hero-value">' + esc(m.rr_label) + '</div>' +
        '<div class="tv-vj-hero-sub">' + esc(sub) + '</div></div>';
    } else if (m.sl_pips != null) {
      hero = '<div class="tv-vj-hero"><div class="tv-vj-hero-kicker">Risk</div>' +
        '<div class="tv-vj-hero-value">' + esc(m.sl_pips + ' to stop') + '</div>' +
        '<div class="tv-vj-hero-sub">Target not set yet</div></div>';
    }
    var facts = [
      [side + ' ' + (d.symbol || ''), status],
      ['In', d.entry_price != null ? d.entry_price : '—'],
      ['Stop', d.stop_loss != null ? d.stop_loss : '—'],
      ['Target', d.take_profit != null ? d.take_profit : '—']
    ];
    if (d.status === 'closed') facts.push(['Out', d.exit_price != null ? d.exit_price : '—']);
    if (m.rr_label) facts.push(['R:R', m.rr_label]);
    if (m.profit_loss != null) facts.push(['P/L', m.profit_loss]);
    if (d.lot_size != null) facts.push(['Size', d.lot_size]);
    if (d.session_type) facts.push(['Session', d.session_type]);
    if (d.timeframe && d.timeframe !== 'unspecified') facts.push(['Timeframe', d.timeframe]);
    if (d.entry_time && d.entry_time !== 'unspecified') facts.push(['Time', d.entry_time]);
    if (d.confidence_level != null && d.confidence_level !== '') facts.push(['Confidence', d.confidence_level + '/10']);

    function narrative(label, text) {
      if (!text || text === 'skipped') return '';
      return '<div class="tv-vj-story-block">' +
        '<span class="tv-vj-story-label">' + esc(label) + '</span>' +
        '<p class="tv-vj-story-text">' + esc(text) + '</p></div>';
    }

    var html = '<article class="tv-vj-card">' + hero;
    html += '<h2>' + esc(facts[0][0]) + ' <span>' + esc(facts[0][1]) + '</span></h2>';
    facts.slice(1).forEach(function (row) {
      html += '<div class="tv-vj-row"><span>' + esc(row[0]) + '</span><strong>' + esc(row[1]) + '</strong></div>';
    });
    if (d.setup_tags && d.setup_tags.length) {
      html += narrative('Setup', d.setup_tags.join(', '));
    }
    journalSections(d).forEach(function (s) {
      html += narrative(s.label, s.text);
    });
    html += '<p class="tv-vj-save-hint">This is the page. Say save, or tap a number to change it.</p>';
    html += '</article>';
    summaryEl.innerHTML = html;
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c];
    });
  }

  function renderPrompts(askKey) {
    var el = document.getElementById('tv-vj-prompts');
    if (!el) return;
    var sets = {
      confirm_levels: ['Looks right', 'Change something'],
      feeling_during: ['Calm', 'Confident', 'Nervous', 'Patient', 'Frustrated'],
      feeling_after: ['Relieved', 'Calm', 'Annoyed', 'Proud', 'Unsure'],
      confidence_level: ['4', '6', '7', '8', '9', '10'],
      followed_plan: ['Yes', 'Mostly', 'No'],
      managed_note: ['As planned', 'Moved stop', 'Took partials', 'Got out early'],
      mistake: ['No mistake']
    };
    var items = sets[askKey] || [];
    if (!items.length) {
      el.innerHTML = '';
      el.classList.remove('is-on');
      return;
    }
    el.innerHTML = items.map(function (label) {
      return '<button type="button" class="tv-vj-prompt" data-say="' + esc(label) + '">' + esc(label) + '</button>';
    }).join('');
    el.classList.add('is-on');
  }

  function showShot() {
    if (!shotEl) return;
    shotEl.classList.remove('d-none');
    renderPrompts('');
    if (shotEl.scrollIntoView) shotEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    var prompt = document.getElementById('tv-vj-shot-prompt');
    if (prompt) prompt.textContent = 'Add chart photo — before and after.';
    var doneBtn = document.getElementById('tv-vj-shot-done');
    if (doneBtn) doneBtn.classList.toggle('d-none', !(hasBefore || hasAfter));
  }

  function previewInSlot(kind, file) {
    var slot = document.getElementById(kind === 'after' ? 'tv-vj-shot-after' : 'tv-vj-shot-before');
    if (!slot || !file) return;
    var url = URL.createObjectURL(file);
    var img = slot.querySelector('img');
    if (!img) {
      img = document.createElement('img');
      img.alt = kind === 'after' ? 'After chart' : 'Before chart';
      slot.appendChild(img);
    }
    img.src = url;
    slot.classList.add('has-file');
  }

  function previewShot(kind, file) {
    var previews = document.getElementById('tv-vj-shot-previews');
    if (!previews || !file) return;
    var url = URL.createObjectURL(file);
    var existing = previews.querySelector('[data-kind="' + kind + '"]');
    var img = existing || document.createElement('img');
    img.src = url;
    img.alt = kind === 'after' ? 'After chart' : 'Before chart';
    img.setAttribute('data-kind', kind);
    if (!existing) previews.appendChild(img);
  }

  function handleShotFile(kind, file) {
    if (!file) return;
    if (kind === 'after') hasAfter = true;
    else hasBefore = true;
    hasShot = hasBefore || hasAfter;
    previewInSlot(kind, file);
    var doneBtn = document.getElementById('tv-vj-shot-done');
    if (doneBtn) doneBtn.classList.remove('d-none');
    if (kind === 'before' && boot.extractUrl) {
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
        renderChips(draft, lastMetrics || {});
      }).catch(function () {});
    }
  }

  var undoStack = null;

  function showRedo(on) {
    var el = document.getElementById('tv-vj-redo');
    if (el) el.classList.toggle('d-none', !on);
  }

  function rememberTurn() {
    var fields = {};
    if (form) {
      var nodes = form.querySelectorAll('input, select, textarea');
      for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].type === 'file') continue;
        var key = nodes[i].id || nodes[i].name;
        if (!key) continue;
        fields[key] = nodes[i].value;
      }
    }
    undoStack = {
      draft: JSON.parse(JSON.stringify(draft || {})),
      history: history.slice(),
      transcript: transcriptDump.slice(),
      confirming: !!confirming,
      reviewMode: !!reviewMode,
      ai: aiEl ? aiEl.textContent : '',
      fields: fields
    };
  }

  function restoreTurn() {
    if (!undoStack || committing) return;
    stopTTS();
    stopRec(true);
    draft = undoStack.draft || {};
    history = undoStack.history || [];
    transcriptDump = (undoStack.transcript || []).slice();
    confirming = !!undoStack.confirming;
    reviewMode = !!undoStack.reviewMode;
    Object.keys(undoStack.fields || {}).forEach(function (k) { setVal(k, undoStack.fields[k]); });
    if (stage) {
      stage.classList.toggle('is-confirm', confirming);
      stage.classList.remove('is-review');
    }
    if (journalEl) journalEl.classList.add('d-none');
    renderChips(draft, lastMetrics || {});
    setAi(undoStack.ai || 'Tell me the trade.');
    setVal('guide_voice_dump', transcriptDump.join('\n'));
    showRedo(false);
    undoStack = null;
    persistDraft();
    speak('Okay. Say that again.', startRec);
  }

  function sendTurn(text) {
    var spoken = String(text || '').trim();
    if (!spoken) return;
    rememberTurn();
    if (reviewMode && looksLikeSaveConfirm(spoken)) {
      clearPersisted();
      if (form.requestSubmit) form.requestSubmit();
      else form.submit();
      return;
    }
    if (fixField) {
      var labels = {
        symbol: 'market',
        trade_type: 'side',
        entry_price: 'entry',
        stop_loss: 'stop',
        take_profit: 'target',
        exit_price: 'exit',
        session_type: 'session',
        lot_size: 'size'
      };
      spoken = 'actually the ' + (labels[fixField] || fixField) + ' was ' + spoken;
      fixField = '';
    }
    if (reviewMode) {
      reviewMode = false;
      if (journalEl) journalEl.classList.add('d-none');
    }
    committing = true;
    setState('thinking');
    setLive(spoken);
    transcriptDump.push(spoken);
    history.push({ role: 'user', content: spoken });
    setVal('guide_voice_dump', transcriptDump.join('\n'));
    fetch(boot.turnUrl || '/trade/api/voice-turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), 'X-CSRF-Token': csrf() },
      body: JSON.stringify({
        transcript: spoken,
        draft: draft,
        history: history,
        has_screenshot: hasBefore && hasAfter,
        has_before: hasBefore,
        has_after: hasAfter,
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
        if (boot.mode === 'quick') draft.voice_mode = 'quick';
        confirming = data.ask_key === 'confirm_levels';
        if (stage) stage.classList.toggle('is-confirm', confirming);
        var check = document.getElementById('tv-vj-check');
        if (check) check.classList.toggle('d-none', !confirming);
        applyForm(data.form, data.instrument);
        renderChips(draft, data.metrics || {});
        setPhase(data.phase || (data.ask_screenshot ? 'charts' : (data.complete ? 'review' : '')));
        setVal('guide_voice_dump', transcriptDump.join('\n'));
        history.push({ role: 'assistant', content: data.reply || '' });
        showRedo(true);
        persistDraft();
        if (pendingEl && (draft.symbol || draft.entry_price != null)) pendingEl.classList.add('d-none');
        if (data.action === 'pause') {
          speak(data.reply || 'I’ll hold this page.', function () {
            window.location.href = boot.listUrl || '/trade/';
          });
          return;
        }
        renderPrompts(data.ask_screenshot ? '' : (data.ask_key || ''));
        if (data.ask_screenshot && shotEl) showShot(data.screenshot_kind || 'before');
        else if (shotEl && !data.ask_screenshot) shotEl.classList.add('d-none');
        if ((data.complete && !data.ask_screenshot) || data.action === 'finish') {
          if (!(data.instrument && data.instrument.id) && !val('instrument_id')) {
            speak('I didn’t catch the market. Say the name once more?', startRec);
            return;
          }
          enterReview(data);
          return;
        }
        speak(data.reply, function () {
          if (reviewMode) return;
          if (data.ask_screenshot) {
            setState('waiting');
            setPhase('charts');
            return;
          }
          startRec();
        });
      })
      .catch(function () {
        committing = false;
        speak('I missed that. Try once more.', startRec);
      });
  }

  function enterReview(data) {
    stopRec(true);
    stopTTS();
    reviewMode = true;
    renderPrompts('');
    setState('review');
    setPhase('review');
    setLive('');
    if (shotEl && hasBefore && hasAfter) shotEl.classList.add('d-none');
    if (journalEl) journalEl.classList.remove('d-none');
    var slip = document.getElementById('tv-vj-slip');
    if (slip) slip.classList.add('d-none');
    if (stage) {
      stage.classList.remove('is-slip');
      stage.classList.add('is-review');
    }
    setVal('guide_voice_dump', transcriptDump.join('\n'));
    renderJournal(data);
    persistDraft();
    speak(data && data.reply ? data.reply : 'Got it. Say save when it looks right.', function () {
      if (reviewMode) startRec();
    });
  }

  function begin() {
    if (state !== 'idle' && state !== 'review' && !reviewMode) return;
    if (reviewMode || state === 'review') startFresh();
    reviewMode = false;
    if (journalEl) journalEl.classList.add('d-none');
    unlockAudio();
    var opening = boot.mode === 'quick'
      ? 'What price did you enter at?'
      : (boot.complete && boot.complete.symbol
        ? ('Let’s finish the notes on ' + boot.complete.symbol + '. What happened?')
        : (draft && draft.symbol
          ? ('Picking up on ' + draft.symbol + '. What else?')
          : 'What price did you enter at?'));
    ensureStream().then(function (stream) {
      attachAnalyser(stream);
      if (!rec.raf) drawOrb();
      speak(opening, startRec);
    }).catch(function () {
      showErr(window.isSecureContext
        ? 'Allow the microphone, then tap again — or type below.'
        : 'Voice needs HTTPS — you can still type below.');
      setState('idle');
    });
  }

  function submitTyped() {
    if (!typeInput || committing) return;
    var text = String(typeInput.value || '').trim();
    if (!text) return;
    typeInput.value = '';
    stopRec(true);
    stopTTS();
    sendTurn(text);
  }

  markVoice(voiceId);
  warmVoice();
  var voiceRow = document.getElementById('tv-vj-voices');
  if (voiceRow) {
    voiceRow.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('[data-voice]') : null;
      if (!btn || committing) return;
      var id = btn.getAttribute('data-voice');
      var preview = state === 'idle';
      markVoice(id);
      if (!preview) return;
      stopTTS();
      var preset = VOICE_PRESETS[voiceId] || VOICE_PRESETS.marin;
      speak(preset.sample, function () {
        if (state === 'speaking') setState('idle');
      });
    });
  }
  if (window.speechSynthesis && window.speechSynthesis.getVoices) {
    window.speechSynthesis.getVoices();
  }

  if (orbBtn) {
    orbBtn.addEventListener('click', function () {
      if (state === 'idle' || state === 'review') begin();
      else if (state === 'waiting') startRec();
      else if (state === 'listening') stopRec(false);
      else if (state === 'speaking') {
        stopTTS();
        setTimeout(startRec, 220);
      }
    });
  }

  function onFixClick(ev) {
    var node = ev.target.closest('[data-fix]');
    if (!node || node.classList.contains('is-quiet')) return;
    askFix(node.getAttribute('data-fix'));
  }
  var chipsEl = document.getElementById('tv-vj-chips');
  if (chipsEl) {
    chipsEl.addEventListener('click', onFixClick);
    var slipEl = document.getElementById('tv-vj-slip');
    if (slipEl) slipEl.addEventListener('click', onFixClick);
    chipsEl.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var node = ev.target.closest('[data-fix]');
      if (!node) return;
      ev.preventDefault();
      askFix(node.getAttribute('data-fix'));
    });
  }

  if (typeSend) typeSend.addEventListener('click', submitTyped);
  if (typeInput) {
    typeInput.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        submitTyped();
      }
    });
  }

  var redoBtn = document.getElementById('tv-vj-redo-btn');
  if (redoBtn) redoBtn.addEventListener('click', restoreTurn);

  var promptEl = document.getElementById('tv-vj-prompts');
  if (promptEl) {
    promptEl.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('[data-say]') : null;
      if (!btn || committing) return;
      var said = btn.getAttribute('data-say') || '';
      if (!said) return;
      if (/^looks right$/i.test(said)) {
        stopRec(true);
        sendTurn('yes that looks right');
        return;
      }
      if (/^followed my rules$/i.test(said)) {
        stopRec(true);
        sendTurn('yes I followed my rules');
        return;
      }
      if (/^about an 8$/i.test(said)) {
        stopRec(true);
        sendTurn('about an 8, I felt calm');
        return;
      }
      if (/^change something$/i.test(said)) {
        stopRec(true);
        setAi('Tap the one that’s wrong.');
        if (chipHint) {
          chipHint.textContent = 'Tap the one that’s wrong';
          chipHint.classList.remove('d-none');
        }
        return;
      }
      if (/^\d+$/.test(said)) said = said + ' out of ten';
      else if (/^(yes|no|mostly)$/i.test(said)) said = said.toLowerCase() === 'yes'
        ? 'yes I followed my rules'
        : (said.toLowerCase() === 'no' ? 'no I broke my rules' : 'mostly on plan');
      else if (/as planned/i.test(said)) said = 'as planned, left the stop';
      else if (/moved stop/i.test(said)) said = 'I moved the stop';
      else if (/partials/i.test(said)) said = 'I took partials';
      else if (/out early/i.test(said)) said = 'I got out early';
      else if (/no mistake/i.test(said)) said = 'no mistake';
      else said = 'I felt ' + said.toLowerCase();
      stopRec(true);
      sendTurn(said);
    });
  }
  var shotDone = document.getElementById('tv-vj-shot-done');
  if (shotDone) {
    shotDone.addEventListener('click', function () {
      if (!(hasBefore || hasAfter)) return;
      if (shotEl) shotEl.classList.add('d-none');
      sendTurn('I uploaded the chart.');
    });
  }
  document.getElementById('tv-vj-shot-before') && document.getElementById('tv-vj-shot-before').addEventListener('click', function () {
    var input = document.getElementById('before_screenshot');
    if (input) input.click();
  });
  document.getElementById('tv-vj-shot-after') && document.getElementById('tv-vj-shot-after').addEventListener('click', function () {
    var input = document.getElementById('after_screenshot');
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
      handleShotFile('before', beforeInput.files && beforeInput.files[0]);
    });
  }
  var afterInput = document.getElementById('after_screenshot');
  if (afterInput) {
    afterInput.addEventListener('change', function () {
      handleShotFile('after', afterInput.files && afterInput.files[0]);
    });
  }

  document.getElementById('tv-vj-fix') && document.getElementById('tv-vj-fix').addEventListener('click', function () {
    if (journalEl) journalEl.classList.add('d-none');
    reviewMode = false;
    skipShot = true;
    speak('Which part should I change?', startRec);
  });

  form.addEventListener('submit', function () {
    markJournalSaved();
    if (!val('lot_size')) setVal('lot_size', '1');
    var why = val('guide_why') || val('pre_trade_plan');
    if (why && !val('pre_trade_plan')) setVal('pre_trade_plan', why);
    // Structured review — never paste the full multi-turn dump into notes.
    var post = val('guide_what_happened') || val('post_trade_notes');
    if (!post && val('guide_feeling_after')) post = 'Feeling after: ' + val('guide_feeling_after');
    if (post && !val('post_trade_notes')) setVal('post_trade_notes', post);
    var lessons = val('lessons_learned');
    if (!lessons) {
      var bits = [];
      if (draft && draft.lessons && draft.lessons !== 'skipped') bits.push(draft.lessons);
      if (val('guide_reflection')) bits.push('Next time: ' + val('guide_reflection'));
      lessons = bits.join('\n');
      if (lessons) setVal('lessons_learned', lessons);
    }
    clearPersisted();
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
    stopTTS();
  });

  seedFromBoot();
  if (!rec.raf) drawOrb();
  syncComposer();

  var newTradeBtn = document.getElementById('tv-vj-new');
  if (newTradeBtn) {
    newTradeBtn.addEventListener('click', function () {
      if (committing) return;
      stopRec(true);
      stopTTS();
      startFresh();
    });
  }

  window.addEventListener('pageshow', function (ev) {
    if (!ev || !ev.persisted) return;
    if (boot.complete && boot.complete.symbol) return;
    if (journalSaved || savedMarkOn()) startFresh();
  });

  window.addEventListener('pagehide', function () {
    if (journalSaved || savedMarkOn()) {
      clearPersisted();
      stopTTS();
      if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
      cancelAnimationFrame(rec.raf);
      return;
    }
    persistDraft();
    stopTTS();
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
    cancelAnimationFrame(rec.raf);
  });
})();
