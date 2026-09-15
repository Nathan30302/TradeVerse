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
  var typeInput = document.getElementById('tv-vj-type-input');
  var typeSend = document.getElementById('tv-vj-type-send');
  var chipHint = document.getElementById('tv-vj-chip-hint');
  var pendingEl = document.getElementById('tv-vj-pending');

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

  function setState(next) {
    state = next;
    if (stage) stage.setAttribute('data-state', next);
    if (statusEl) {
      statusEl.textContent =
        next === 'listening' ? 'Listening' :
        next === 'thinking' ? 'Gathering the page' :
        next === 'speaking' ? 'Speaking' :
        next === 'waiting' ? 'Add your charts' :
        next === 'review' ? 'Ready to save' :
        'Tap the ink when you’re ready';
    }
    syncComposer();
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

  function persistDraft() {
    try {
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
      var pulse = speaking ? (0.1 + rec.voiceRms * 0.55 + Math.sin(Date.now() / 420 + idx) * 0.04) : 0.045;
      var rad = speaking ? (140 + rec.voiceRms * 220) : 110;
      var g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, rad);
      g.addColorStop(0, rgbOf(gold, pulse));
      g.addColorStop(0.45, rgbOf(gold, pulse * 0.35));
      g.addColorStop(1, rgbOf(gold, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(c.x, c.y, rad, 0, Math.PI * 2);
      ctx.fill();
    });
    if (speaking && Date.now() - rec.rippleAt > 90) {
      rec.rippleAt = Date.now();
      var cx = w / 2;
      var cy = Math.min(h * 0.28, 190);
      // Center motes
      rec.waterRipples.push({
        x: cx + (Math.random() - 0.5) * 40,
        y: cy + (Math.random() - 0.5) * 28,
        r: 4 + Math.random() * 8,
        a: 0.2 + rec.voiceRms * 0.55,
        grow: 0.7 + rec.voiceRms * 2.2,
        kind: 'mote'
      });
      // Corner ink blooms
      corners.forEach(function (c) {
        if (Math.random() > 0.55) return;
        rec.waterRipples.push({
          x: c.x + (c.x === 0 ? 28 : -28) + (Math.random() - 0.5) * 18,
          y: c.y + (c.y === 0 ? 28 : -28) + (Math.random() - 0.5) * 18,
          r: 10 + Math.random() * 16,
          a: 0.22 + rec.voiceRms * 0.5,
          grow: 1.1 + rec.voiceRms * 3.4,
          kind: 'corner'
        });
      });
      if (rec.waterRipples.length > 36) rec.waterRipples.splice(0, rec.waterRipples.length - 36);
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
      rec.sr.maxAlternatives = 3;
      rec.sr.onresult = function (ev) {
        var finalTxt = '';
        var interim = '';
        for (var i = ev.resultIndex; i < ev.results.length; i++) {
          var best = ev.results[i][0].transcript;
          // Prefer the alternative that knows more trading words.
          if (ev.results[i].length > 1) {
            var topScore = tradingScore(best);
            for (var a = 1; a < ev.results[i].length; a++) {
              var alt = ev.results[i][a].transcript;
              var sc = tradingScore(alt);
              if (sc > topScore) {
                best = alt;
                topScore = sc;
              }
            }
          }
          if (ev.results[i].isFinal) finalTxt += best;
          else interim += best;
        }
        if (finalTxt) rec.text = (rec.text + ' ' + finalTxt).trim();
        var shown = (rec.text + (interim ? ' ' + interim : '')).replace(/\s+/g, ' ').trim();
        setLive(shown);
        if (shown) {
          clearTimeout(rec.silence);
          rec.silence = setTimeout(function () {
            if (rec.recording) stopRec(false);
          }, 2600);
        }
      };
      rec.sr.onerror = function () {};
      rec.sr.onend = function () {
        if (rec.recording && rec.sr) {
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
        rec.mr = rec.mime ? new MediaRecorder(stream, { mimeType: rec.mime }) : new MediaRecorder(stream);
      } catch (e) {
        rec.mr = new MediaRecorder(stream);
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

  var TRADE_WORDS = [
    'long', 'short', 'buy', 'sell', 'entry', 'stop', 'target', 'tp', 'sl',
    'gold', 'eurusd', 'gbpusd', 'us30', 'nas100', 'xauusd', 'bitcoin',
    'london', 'asia', 'overlap', 'breakout', 'retest', 'liquidity', 'sweep',
    'order block', 'bos', 'choch', 'fvg', 'partials', 'lot', 'pips', 'session'
  ];

  function tradingScore(text) {
    var t = String(text || '').toLowerCase();
    var n = 0;
    TRADE_WORDS.forEach(function (w) {
      if (t.indexOf(w) !== -1) n += 1;
    });
    // Prefer keeping precise decimals / prices
    if (/\d+\.\d+/.test(t)) n += 2;
    if (/\b\d{3,5}\b/.test(t)) n += 1;
    return n;
  }

  function pickTranscript(whisper, local) {
    whisper = String(whisper || '').trim();
    local = String(local || '').trim();
    if (isPromptLeak(whisper)) whisper = '';
    if (looksLikeEcho(whisper)) whisper = '';
    if (looksLikeEcho(local)) local = '';
    if (!whisper) return local;
    if (!local) return whisper;
    var localWords = tokensOf(local).length;
    // Short confirms / single numbers: keep the live caption exact.
    if (localWords <= 4) return local;
    var ws = tradingScore(whisper);
    var ls = tradingScore(local);
    var wl = whisper.replace(/\s/g, '').length;
    var ll = local.replace(/\s/g, '').length;
    // Prefer the fuller, more trading-aware transcript so we keep exact words.
    if (ws > ls && wl >= ll * 0.85) return whisper;
    if (wl > ll * 1.35 && ws >= ls) return whisper;
    if (ll >= 2) return local;
    return whisper;
  }

  function finishUtterance(srText, blob) {
    var local = String(srText || '').trim();
    if (looksLikeEcho(local)) local = '';
    var blobOk = !!(blob && blob.size > 900 && boot.transcribeEnabled);
    // Always reconcile with Whisper when we can — keeps exact spoken words.
    if (blobOk) {
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
          if (text) {
            setLive(text);
            sendTurn(text);
          } else startRec();
        })
        .catch(function () {
          committing = false;
          if (local) sendTurn(local);
          else startRec();
        });
      return;
    }
    if (local && local.replace(/\s/g, '').length >= 2) {
      setLive(local);
      sendTurn(local);
      return;
    }
    setLive('');
    startRec();
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
    if (d.session_type) chips.push({ t: String(d.session_type).replace(' Session', ''), k: '', f: 'session_type' });
    if (d.lot_size != null && Number(d.lot_size) !== 1) chips.push({ t: d.lot_size + ' lot', k: '', f: 'lot_size' });
    el.innerHTML = chips.map(function (c) {
      var tap = c.f ? ' is-tap' : '';
      var attr = c.f ? ' data-fix="' + esc(c.f) + '" role="button" tabindex="0"' : '';
      return '<span class="tv-vj-chip ' + c.k + tap + '"' + attr + '>' + esc(c.t) + '</span>';
    }).join('');
    el.classList.toggle('is-on', chips.length > 0);
    if (chipHint) chipHint.classList.toggle('d-none', chips.filter(function (c) { return c.f; }).length < 1);
  }

  function askFix(field) {
    fixField = field || '';
    reviewMode = false;
    var prompts = {
      symbol: 'What market was it?',
      trade_type: 'Long or short?',
      entry_price: 'What was the entry?',
      stop_loss: 'Where was the stop?',
      take_profit: 'What was the target?',
      exit_price: 'Where did you get out?',
      session_type: 'Which session?',
      lot_size: 'What size were you trading?'
    };
    var line = prompts[fixField] || 'What should I change?';
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
      if (m.tp_pips != null) sub = 'Risk ' + m.sl_pips + ' to make ' + m.tp_pips;
      hero = '<div class="tv-vj-hero"><div class="tv-vj-hero-kicker">Planned return</div>' +
        '<div class="tv-vj-hero-value">' + esc(m.rr_label) + '</div>' +
        '<div class="tv-vj-hero-sub">' + esc(sub) + '</div></div>';
    } else if (m.sl_pips != null) {
      hero = '<div class="tv-vj-hero"><div class="tv-vj-hero-kicker">Risk</div>' +
        '<div class="tv-vj-hero-value">' + esc(m.sl_pips + ' to stop') + '</div>' +
        '<div class="tv-vj-hero-sub">Target not set yet</div></div>';
    }
    var rows = [
      [side + ' ' + (d.symbol || ''), status],
      ['In', d.entry_price != null ? d.entry_price : '—'],
      ['Stop', d.stop_loss != null ? d.stop_loss : '—'],
      ['Target', d.take_profit != null ? d.take_profit : '—']
    ];
    if (d.status === 'closed') rows.push(['Out', d.exit_price != null ? d.exit_price : '—']);
    if (m.rr_label) rows.push(['R:R', m.rr_label]);
    if (m.profit_loss != null) rows.push(['P/L', m.profit_loss]);
    if (d.session_type) rows.push(['Session', d.session_type]);
    if (d.entry_time && d.entry_time !== 'unspecified') rows.push(['Time', d.entry_time]);
    if (d.setup_tags && d.setup_tags.length) rows.push(['Setup', d.setup_tags.join(', ')]);
    if (d.emotions && d.emotions.length) rows.push(['Feel', d.emotions.join(', ')]);
    if (d.thesis_notes && d.thesis_notes !== 'skipped') rows.push(['Why', d.thesis_notes]);
    if (d.followed_plan && d.followed_plan !== 'skipped') {
      rows.push(['Rules', d.followed_plan === 'yes' ? 'Followed' : (d.followed_plan === 'mostly' ? 'Mostly' : 'Broke rules')]);
    }
    if (d.feeling_during && d.feeling_during !== 'skipped') rows.push(['During', d.feeling_during]);
    if (d.feeling_after && d.feeling_after !== 'skipped') rows.push(['After', d.feeling_after]);
    if (d.lessons && d.lessons !== 'skipped') rows.push(['Learned', d.lessons]);
    if (d.improve_next && d.improve_next !== 'skipped') rows.push(['Next time', d.improve_next]);
    var html = '<article class="tv-vj-card">' + hero;
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

  function showShot(kind) {
    shotKind = kind === 'after' ? 'after' : 'before';
    if (!shotEl) return;
    shotEl.classList.remove('d-none');
    var prompt = document.getElementById('tv-vj-shot-prompt');
    if (prompt) {
      prompt.textContent = shotKind === 'after'
        ? 'And the after chart?'
        : 'Got a before-trade screenshot?';
    }
    var beforeBtn = document.getElementById('tv-vj-shot-before');
    var afterBtn = document.getElementById('tv-vj-shot-after');
    if (beforeBtn) beforeBtn.classList.toggle('is-active', shotKind !== 'after');
    if (afterBtn) afterBtn.classList.toggle('is-active', shotKind === 'after');
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
    previewShot(kind, file);
    var said = kind === 'after' ? 'I uploaded the after chart.' : 'I uploaded the before chart.';
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
        sendTurn(said);
      }).catch(function () {
        sendTurn(said);
      });
    } else {
      sendTurn(said);
    }
  }

  function sendTurn(text) {
    var spoken = String(text || '').trim();
    if (!spoken) return;
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
        applyForm(data.form, data.instrument);
        renderChips(draft, data.metrics || {});
        setVal('guide_voice_dump', transcriptDump.join('\n'));
        history.push({ role: 'assistant', content: data.reply || '' });
        persistDraft();
        if (pendingEl && (draft.symbol || draft.entry_price != null)) pendingEl.classList.add('d-none');
        if (data.ask_screenshot && shotEl) showShot(data.screenshot_kind || 'before');
        if (data.complete && !data.ask_screenshot) {
          if (!(data.instrument && data.instrument.id) && !val('instrument_id')) {
            speak('I didn’t catch the market — say the ticker once more?', startRec);
            return;
          }
          enterReview(data);
          return;
        }
        speak(data.reply, function () {
          if (reviewMode) return;
          if (data.ask_screenshot) {
            setState('waiting');
            return;
          }
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
    reviewMode = true;
    setState('review');
    setLive('');
    if (shotEl && hasBefore && hasAfter) shotEl.classList.add('d-none');
    if (journalEl) journalEl.classList.remove('d-none');
    setVal('guide_voice_dump', transcriptDump.join('\n'));
    renderJournal(data);
    persistDraft();
    speak(data && data.reply ? data.reply : 'Got it — say save when it looks right.', function () {
      if (reviewMode) startRec();
    });
  }

  function begin() {
    if (state !== 'idle' && state !== 'review' && !reviewMode) return;
    reviewMode = false;
    if (journalEl) journalEl.classList.add('d-none');
    unlockAudio();
    var opening = boot.mode === 'quick'
      ? 'Give me the short version — pair, side, levels.'
      : (boot.complete && boot.complete.symbol
        ? ('Let’s finish the notes on ' + boot.complete.symbol + '. What happened?')
        : (draft && draft.symbol
          ? ('Picking up on ' + draft.symbol + ' — what else?')
          : 'Hey — tell me about the trade.'));
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

  var chipsEl = document.getElementById('tv-vj-chips');
  if (chipsEl) {
    chipsEl.addEventListener('click', function (ev) {
      var node = ev.target.closest('[data-fix]');
      if (!node) return;
      askFix(node.getAttribute('data-fix'));
    });
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
    speak('What should I change?', startRec);
  });

  form.addEventListener('submit', function () {
    if (!val('lot_size')) setVal('lot_size', '1');
    var why = val('guide_why') || val('guide_voice_dump');
    if (why && !val('pre_trade_plan')) setVal('pre_trade_plan', why);
    var post = val('guide_voice_dump') || why;
    if (post && !val('post_trade_notes')) setVal('post_trade_notes', post);
    clearPersisted();
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
    stopTTS();
  });

  seedFromBoot();
  if (!rec.raf) drawOrb();
  syncComposer();

  window.addEventListener('pagehide', function () {
    persistDraft();
    stopTTS();
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
    cancelAnimationFrame(rec.raf);
  });
})();
