/**
 * AI Buddy page — chat, Trade Doctor, Coach Talk, pin/save helpers.
 */
(function (global) {
  'use strict';

  function getCsrf() {
    if (typeof global.tvGetCsrf === 'function') {
      var t = global.tvGetCsrf();
      if (t) return t;
    }
    var el = document.querySelector("input[name='csrf_token']");
    return el ? el.value : '';
  }

  function initAiBuddyPage() {
    var root = document.getElementById('ai-page-root');
    if (!root) return;

    var CSRF = getCsrf();
    var AI_QUERY_URL = root.getAttribute('data-query-url') || '';
    var TRADE_DOCTOR_URL = root.getAttribute('data-trade-doctor-url') || '';
    var PIN_URL = root.getAttribute('data-pin-url') || '';
    var FOCUS_URL = root.getAttribute('data-focus-url') || '';
    var VOICE_TEXT = root.getAttribute('data-voice') || '';
    var USERNAME = root.getAttribute('data-username') || '';
    var SPEAK_URL = root.getAttribute('data-speak-url') || '';
    var BRIEFING_URL = root.getAttribute('data-briefing-url') || '';
    var HAS_NEURAL = root.getAttribute('data-neural') === '1';
    var neuralVoiceId = 'coral';
    var neuralAudio = null;
    var STATS_URL = '/dashboard/api/stats';

    var HISTORY = [];
    var coachActive = false;
    var coachIntroShown = false;
    var recognition = null;
    var isSpeaking = false;
    var isListening = false;
    var requestInFlight = false;
    var voiceSendTimer = null;
    var lastTradeDoctor = null;
    var selectedVoiceURI = '';
    var waveRaf = null;
    var micStream = null;
    var micAnalyser = null;
    var micAudioCtx = null;

    var tvCurrency = root.getAttribute('data-currency') || 'USD';
    var tvFx = parseFloat(root.getAttribute('data-fx') || '1') || 1;

    function fmtMoney(n) {
      if (typeof n !== 'number' || isNaN(n)) return '—';
      var v = n * tvFx;
      try {
        return new Intl.NumberFormat(undefined, { style: 'currency', currency: tvCurrency }).format(v);
      } catch (e) {
        return (v >= 0 ? '' : '-') + '$' + Math.abs(v).toFixed(2);
      }
    }

    function refreshBasis() {
      fetch(STATS_URL, { headers: { Accept: 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var t = document.getElementById('aiBasisTrades');
          var wr = document.getElementById('aiBasisWR');
          var pnl = document.getElementById('aiBasisPNL');
          if (t) t.textContent = String(d && d.wins_7d !== undefined ? (d.wins_7d || 0) + (d.losses_7d || 0) : (d.trades_today || '—'));
          if (wr) wr.textContent = (d && typeof d.win_rate_7d === 'number') ? d.win_rate_7d.toFixed(1) + '%' : '—';
          if (pnl) pnl.textContent = (d && typeof d.pnl_7d === 'number') ? fmtMoney(d.pnl_7d) : '—';
        })
        .catch(function () {});
    }

    function showAiTab(name) {
      // Legacy no-op — Coach home is a single canvas now.
      try { sessionStorage.setItem('tv_ai_tab', name || 'today'); } catch (e) {}
    }

    function ensureChatTab() {
      showAiTab('today');
      var card = document.getElementById('ai-chat-card');
      if (card && card.scrollIntoView) {
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      var q = document.getElementById('aiQuestion');
      if (q) {
        try { q.focus(); } catch (e) {}
      }
    }

    function scrollChatToBottom() {
      var thread = document.getElementById('aiChat');
      if (thread) thread.scrollTop = thread.scrollHeight;
    }

    function updateEmptyHints() {
      var hints = document.getElementById('aiEmptyHints');
      if (!hints) return;
      if (HISTORY.length > 0) hints.classList.add('d-none');
      else hints.classList.remove('d-none');
    }

    function getSelectedVoice() {
      try {
        var voices = global.speechSynthesis ? global.speechSynthesis.getVoices() : [];
        if (selectedVoiceURI) {
          for (var i = 0; i < voices.length; i++) {
            if (voices[i].voiceURI === selectedVoiceURI) return voices[i];
          }
        }
        for (var j = 0; j < voices.length; j++) {
          if ((voices[j].lang || '').toLowerCase().indexOf('en') === 0) return voices[j];
        }
        return voices[0] || null;
      } catch (e) {
        return null;
      }
    }

    function pickEnglishVoice() {
      return getSelectedVoice();
    }

    function populateVoiceSelects() {
      var neuralSel = HAS_NEURAL;
      var selects = [
        document.getElementById('aiVoiceSelect'),
        document.getElementById('aiVoiceSelectComposer'),
      ];
      try {
        selectedVoiceURI = localStorage.getItem('tv_ai_voice_uri') || selectedVoiceURI;
        neuralVoiceId = localStorage.getItem('tv_ai_neural_voice') || neuralVoiceId;
      } catch (e) {}

      if (neuralSel) {
        var neuralList = ['coral', 'verse', 'alloy', 'nova', 'sage', 'shimmer', 'echo', 'fable', 'onyx', 'ash', 'ballad'];
        selects.forEach(function (sel) {
          if (!sel) return;
          sel.textContent = '';
          neuralList.forEach(function (v) {
            var opt = document.createElement('option');
            opt.value = 'neural:' + v;
            opt.textContent = v.charAt(0).toUpperCase() + v.slice(1) + ' (neural)';
            sel.appendChild(opt);
          });
          var want = 'neural:' + neuralVoiceId;
          sel.value = want;
          if (!sel.value) sel.value = 'neural:coral';
          selectedVoiceURI = sel.value;
        });
        return;
      }

      if (!global.speechSynthesis) return;
      var voices = global.speechSynthesis.getVoices() || [];
      var english = voices.filter(function (v) {
        return (v.lang || '').toLowerCase().indexOf('en') === 0;
      });
      var list = english.length ? english : voices;
      selects.forEach(function (sel) {
        if (!sel) return;
        var prev = sel.value || selectedVoiceURI;
        sel.textContent = '';
        list.forEach(function (v) {
          var opt = document.createElement('option');
          opt.value = v.voiceURI;
          opt.textContent = (v.name || 'Voice') + (v.lang ? ' (' + v.lang + ')' : '');
          sel.appendChild(opt);
        });
        if (prev) sel.value = prev;
        if (!sel.value && list[0]) sel.value = list[0].voiceURI;
        selectedVoiceURI = sel.value || selectedVoiceURI;
      });
    }

    function bindVoiceSelect(sel) {
      if (!sel) return;
      sel.addEventListener('change', function () {
        selectedVoiceURI = sel.value || '';
        if (selectedVoiceURI.indexOf('neural:') === 0) {
          neuralVoiceId = selectedVoiceURI.slice(7) || 'coral';
          try { localStorage.setItem('tv_ai_neural_voice', neuralVoiceId); } catch (e) {}
        }
        try { localStorage.setItem('tv_ai_voice_uri', selectedVoiceURI); } catch (e) {}
        var other = sel.id === 'aiVoiceSelect'
          ? document.getElementById('aiVoiceSelectComposer')
          : document.getElementById('aiVoiceSelect');
        if (other) other.value = selectedVoiceURI;
      });
    }

    function stopNeuralAudio() {
      if (neuralAudio) {
        try { neuralAudio.pause(); } catch (e) {}
        try { URL.revokeObjectURL(neuralAudio._tvUrl); } catch (e) {}
        neuralAudio = null;
      }
    }

    function speakNeural(text) {
      return new Promise(function (resolve) {
        if (!SPEAK_URL || !HAS_NEURAL) { resolve(false); return; }
        stopNeuralAudio();
        stopListening();
        try { global.speechSynthesis && global.speechSynthesis.cancel(); } catch (e) {}
        isSpeaking = true;
        setCoachStatus('speaking', 'Speaking the answer…');
        if (coachActive) setTalkTranscript('AI Coach is speaking…', false);
        fetch(SPEAK_URL, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'audio/mpeg',
            'X-CSRFToken': CSRF,
            'X-CSRF-Token': CSRF,
          },
          body: JSON.stringify({ text: text, voice: neuralVoiceId || 'coral' }),
        })
          .then(function (r) {
            if (!r.ok) throw new Error('tts');
            return r.blob();
          })
          .then(function (blob) {
            var url = URL.createObjectURL(blob);
            var audio = new Audio(url);
            audio._tvUrl = url;
            neuralAudio = audio;
            audio.onended = audio.onerror = function () {
              isSpeaking = false;
              stopNeuralAudio();
              if (coachActive && !requestInFlight) {
                setCoachStatus('listening', 'Listening… speak your next question.');
                setTalkTranscript('Your turn — I’m listening.', false);
              } else if (!coachActive) {
                setCoachStatus('idle', 'Pick an action above, or type a question below.');
              }
              resolve(true);
            };
            return audio.play().then(function () {}, function () { throw new Error('play'); });
          })
          .catch(function () {
            isSpeaking = false;
            resolve(false);
          });
      });
    }

    function speakBrowser(text) {
      return new Promise(function (resolve) {
        if (!global.speechSynthesis) { resolve(); return; }
        stopListening();
        global.speechSynthesis.cancel();
        var plain = String(text || '').replace(/\*\*/g, '');
        var u = new SpeechSynthesisUtterance(plain);
        u.rate = 1.02;
        u.pitch = 1.03;
        var v = pickEnglishVoice();
        if (v) u.voice = v;
        isSpeaking = true;
        setCoachStatus('speaking', 'Speaking the answer…');
        var coachBtn = document.getElementById('coachTalkBtn');
        if (coachBtn) coachBtn.classList.add('tv-speaking');
        u.onend = u.onerror = function () {
          isSpeaking = false;
          if (coachBtn) coachBtn.classList.remove('tv-speaking');
          if (coachActive && !requestInFlight) {
            setCoachStatus('listening', 'Listening… speak your next question.');
            setTalkTranscript('Your turn — I’m listening.', false);
          } else if (!coachActive) {
            setCoachStatus('idle', 'Pick an action above, or type a question below.');
          }
          resolve();
        };
        global.speechSynthesis.speak(u);
      });
    }

    function speakText(text) {
      return speakNeural(text).then(function (ok) {
        if (ok) return;
        return speakBrowser(text);
      });
    }

    function setTalkOverlayOpen(open) {
      var overlay = document.getElementById('tvTalkOverlay');
      if (!overlay) return;
      overlay.classList.toggle('is-open', !!open);
      overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
      if (!open) {
        overlay.classList.remove('is-listening', 'is-thinking', 'is-speaking', 'is-error');
        stopWaveform();
      }
    }

    function setTalkTranscript(text, isInterim) {
      var el = document.getElementById('tvTalkTranscript');
      if (!el) return;
      el.textContent = text || (coachActive ? 'Listening…' : 'Start talking — I’ll show your words here.');
      el.classList.toggle('is-interim', !!isInterim);
    }

    function setTalkVisualState(state) {
      var overlay = document.getElementById('tvTalkOverlay');
      var label = document.getElementById('tvTalkState');
      if (!overlay) return;
      overlay.classList.remove('is-listening', 'is-thinking', 'is-speaking', 'is-error');
      if (state === 'listening' || state === 'thinking' || state === 'speaking' || state === 'error') {
        overlay.classList.add('is-' + state);
      }
      if (label) {
        var map = {
          listening: 'Listening',
          thinking: 'Thinking',
          speaking: 'Speaking',
          error: 'Try again',
          idle: 'Ready',
        };
        label.textContent = map[state] || 'Ready';
      }
    }

    function stopWaveform() {
      if (waveRaf) {
        cancelAnimationFrame(waveRaf);
        waveRaf = null;
      }
      if (micStream) {
        try {
          micStream.getTracks().forEach(function (t) { t.stop(); });
        } catch (e) {}
        micStream = null;
      }
      if (micAudioCtx) {
        try { micAudioCtx.close(); } catch (e) {}
        micAudioCtx = null;
      }
      micAnalyser = null;
      var bars = document.querySelectorAll('#tvTalkWave span');
      bars.forEach(function (b) { b.style.height = ''; });
    }

    function startWaveform() {
      stopWaveform();
      var bars = document.querySelectorAll('#tvTalkWave span');
      if (!bars.length || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
      navigator.mediaDevices.getUserMedia({ audio: true, video: false }).then(function (stream) {
        if (!coachActive) {
          stream.getTracks().forEach(function (t) { t.stop(); });
          return;
        }
        micStream = stream;
        var AC = global.AudioContext || global.webkitAudioContext;
        if (!AC) return;
        micAudioCtx = new AC();
        var source = micAudioCtx.createMediaStreamSource(stream);
        micAnalyser = micAudioCtx.createAnalyser();
        micAnalyser.fftSize = 64;
        source.connect(micAnalyser);
        var data = new Uint8Array(micAnalyser.frequencyBinCount);

        function tick() {
          if (!micAnalyser || !coachActive) return;
          micAnalyser.getByteFrequencyData(data);
          var step = Math.max(1, Math.floor(data.length / bars.length));
          for (var i = 0; i < bars.length; i++) {
            var v = data[Math.min(data.length - 1, i * step)] || 0;
            var h = 12 + Math.round((v / 255) * 88);
            bars[i].style.height = h + '%';
          }
          waveRaf = requestAnimationFrame(tick);
        }
        tick();
      }).catch(function () {
        /* CSS fallback animation still runs via .is-listening */
      });
    }

    function setCoachStatus(state, message) {
      var el = document.getElementById('aiCoachStatus');
      if (el) {
        el.classList.remove('is-listening', 'is-thinking', 'is-speaking', 'is-error');
        if (state === 'listening') el.classList.add('is-listening');
        else if (state === 'thinking') el.classList.add('is-thinking');
        else if (state === 'speaking') el.classList.add('is-speaking');
        else if (state === 'error') el.classList.add('is-error');
        if (message) el.textContent = message;
      }
      if (coachActive) setTalkVisualState(state);
    }

    function isVoiceAutoSend() {
      var cb = document.getElementById('aiVoiceAutoSend');
      return !cb || cb.checked;
    }

    function extractTranscript(evt) {
      var interim = [];
      var finals = [];
      if (!evt || !evt.results) return { text: '', isFinal: false };
      for (var i = 0; i < evt.results.length; i++) {
        var bit = evt.results[i];
        if (!bit || !bit[0]) continue;
        var t = (bit[0].transcript || '').trim();
        if (!t) continue;
        if (bit.isFinal) finals.push(t);
        else interim.push(t);
      }
      var text = (finals.length ? finals.join(' ') : interim.join(' ')).trim();
      var isFinal = evt.results.length > 0 && evt.results[evt.results.length - 1].isFinal;
      return { text: text, isFinal: isFinal };
    }

    function clearVoiceSendTimer() {
      if (voiceSendTimer) {
        clearTimeout(voiceSendTimer);
        voiceSendTimer = null;
      }
    }

    function scheduleVoiceSend(transcript) {
      clearVoiceSendTimer();
      var qEl = document.getElementById('aiQuestion');
      if (qEl) {
        qEl.value = transcript;
        qEl.classList.remove('tv-voice-interim');
      }
      setTalkTranscript(transcript, false);
      if (!isVoiceAutoSend()) {
        setCoachStatus('idle', 'Review your message, then tap send.');
        setTalkTranscript(transcript + ' — review and send, or keep talking.', false);
        return;
      }
      setCoachStatus('thinking', 'Sending your question…');
      voiceSendTimer = setTimeout(function () {
        voiceSendTimer = null;
        if (!transcript.trim() || requestInFlight) return;
        onAskClick(transcript);
      }, 450);
    }

    function stopListening() {
      isListening = false;
      var qEl = document.getElementById('aiQuestion');
      if (qEl) qEl.classList.remove('tv-voice-listening', 'tv-voice-interim');
      try {
        if (recognition) recognition.stop();
      } catch (e) {}
    }

    function splitSentences(text) {
      return String(text || '').replace(/\s+/g, ' ').split(/(?<=[.!?])\s+/).map(function (s) { return s.trim(); }).filter(Boolean);
    }

    async function playVoiceReview() {
      if (!VOICE_TEXT) return;
      await speakText(VOICE_TEXT);
    }

    function renderFollowUps(items) {
      var wrap = document.getElementById('aiFollowUps');
      if (!wrap) return;
      wrap.textContent = '';
      if (!items || !items.length) return;
      for (var i = 0; i < items.length; i++) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn btn-sm btn-outline-secondary tv-follow';
        b.textContent = items[i];
        b.setAttribute('data-q', items[i]);
        wrap.appendChild(b);
      }
    }

    function appendChat(role, content, opts) {
      opts = opts || {};
      var chat = document.getElementById('aiChatLog');
      if (!chat) return;
      var bubble = document.createElement('div');
      bubble.className = 'tv-surface soft p-3 mb-2 ' + (role === 'user' ? 'tv-chat-bubble-user' : 'tv-chat-bubble-assistant');
      var head = document.createElement('div');
      head.className = 'd-flex align-items-center justify-content-between gap-2 small tv-muted mb-2';
      var who = document.createElement('div');
      who.textContent = role === 'user' ? (USERNAME ? USERNAME + ' (you)' : 'You') : 'AI Coach';
      head.appendChild(who);
      if (role === 'assistant' && opts.usedWeb !== undefined) {
        var src = document.createElement('span');
        src.className = 'tv-answer-source';
        src.textContent = opts.usedWeb ? 'Pro web' : 'Journal coach';
        src.title = opts.usedWeb ? 'Answer used live web context' : 'Answer from your journal and stats';
        head.appendChild(src);
      }
      if (role === 'assistant') {
        var actions = document.createElement('div');
        actions.className = 'd-flex gap-2 flex-wrap';
        var copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'btn btn-sm btn-outline-secondary';
        copyBtn.textContent = 'Copy';
        copyBtn.addEventListener('click', function () {
          try { navigator.clipboard.writeText(String(content || '')); } catch (e) {}
        });
        var speakBtn = document.createElement('button');
        speakBtn.type = 'button';
        speakBtn.className = 'btn btn-sm btn-outline-secondary';
        speakBtn.textContent = 'Speak';
        speakBtn.addEventListener('click', function () { speakText(String(content || '')); });
        actions.appendChild(copyBtn);
        actions.appendChild(speakBtn);
        head.appendChild(actions);
      }
      var body = document.createElement('div');
      function esc(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      }
      function formatText(s) {
        var safe = esc(s);
        safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        var lines = safe.split('\n');
        var out = [];
        var inList = false;
        for (var j = 0; j < lines.length; j++) {
          var line = lines[j];
          if (line.trim().indexOf('- ') === 0) {
            if (!inList) { out.push("<ul style='margin:0 0 0.5rem 1.25rem;'>"); inList = true; }
            out.push('<li>' + line.trim().slice(2) + '</li>');
          } else {
            if (inList) { out.push('</ul>'); inList = false; }
            if (line.trim() === '') out.push("<div style='height:0.5rem;'></div>");
            else out.push("<div style='white-space:pre-wrap;'>" + line + '</div>');
          }
        }
        if (inList) out.push('</ul>');
        return out.join('');
      }
      body.innerHTML = formatText(content);
      bubble.appendChild(head);
      bubble.appendChild(body);
      chat.appendChild(bubble);
      updateEmptyHints();
      scrollChatToBottom();
      if (!opts.skipHistory) {
        HISTORY.push({ role: role, content: content });
        if (HISTORY.length > 14) HISTORY = HISTORY.slice(-14);
      }
      if (!opts.skipStore) {
        try { sessionStorage.setItem('tv_ai_history', JSON.stringify(HISTORY)); } catch (e) {}
      }
    }

    function setChatBusy(isBusy, questionHint) {
      var btn = document.getElementById('aiSubmitBtn');
      var q = document.getElementById('aiQuestion');
      var chips = document.getElementById('aiQuickChips');
      var tdBtn = document.getElementById('tradeDoctorBtn');
      var busy = !!isBusy;
      if (btn) {
        btn.disabled = busy;
        btn.classList.toggle('loading', busy);
      }
      if (q) q.disabled = busy && !isListening;
      if (chips) {
        chips.querySelectorAll('button').forEach(function (b) { b.disabled = busy; });
      }
      if (tdBtn) tdBtn.disabled = busy;
      var log = document.getElementById('aiChatLog');
      var existing = document.getElementById('aiTyping');
      if (busy && log && !existing) {
        var bubble = document.createElement('div');
        bubble.id = 'aiTyping';
        bubble.className = 'tv-surface soft p-3 mb-2';
        var hint = questionHint ? String(questionHint).trim().slice(0, 100) : '';
        var safeHint = hint.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        var label = hint
          ? '<div class="small tv-muted mb-1 text-truncate" title="' + safeHint + '">Answering: ' + safeHint + '</div>'
          : '<div class="small tv-muted mb-1">AI Coach</div>';
        bubble.innerHTML = label + '<div class="tv-typing" aria-label="Thinking"><span></span><span></span><span></span></div>';
        log.appendChild(bubble);
        scrollChatToBottom();
      } else if (!busy && existing) {
        existing.remove();
      }
      if (busy) {
        stopListening();
        setCoachStatus('thinking', 'Thinking…');
      } else if (coachActive && !isSpeaking) {
        setCoachStatus('listening', 'Listening… speak your question.');
        setTalkTranscript('Your turn — I’m listening.', false);
      } else if (!coachActive) {
        setCoachStatus('idle', 'Type a question, or tap Talk to speak with your coach.');
      }
    }

    function showSuggestedFocus(rule) {
      if (!rule) return;
      var box = document.getElementById('aiSuggestedFocus');
      var txt = document.getElementById('aiSuggestedFocusText');
      if (txt) txt.textContent = rule;
      if (box) box.classList.remove('d-none');
    }

    function applyWeeklyFocus(rule, onDone) {
      if (!FOCUS_URL || !rule) return;
      fetch(FOCUS_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF, 'X-CSRF-Token': CSRF },
        body: JSON.stringify({ rule: rule }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.ok) {
            var inp = document.getElementById('weekly_focus_ai');
            if (inp) inp.value = rule;
            var msg = 'Saved your weekly focus: **' + rule + '**. I’ll score the next trades against this.';
            if (d.compliance && d.compliance.sample_size) {
              msg += '\n\nCurrent adherence: **' + (d.compliance.label || '') + '**';
            } else {
              msg += '\n\nClose a few trades under this rule to unlock adherence %.';
            }
            appendChat('assistant', msg);
          }
          if (onDone) onDone(d);
        })
        .catch(function () {
          appendChat('assistant', 'Could not save weekly focus right now. Use the Coach setup tab.');
        });
    }

    function pinTradeDoctor(d) {
      if (!PIN_URL || !d || !d.leak) return;
      var rule = 'Trade Doctor: ' + d.leak;
      var checklist = d.checklist || [];
      fetch(PIN_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF, 'X-CSRF-Token': CSRF },
        body: JSON.stringify({ pinned_rule: rule, checklist: checklist, source: 'trade_doctor' }),
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res && res.ok) {
            appendChat('assistant', 'Pinned to your dashboard: **' + rule + '**');
          } else {
            appendChat('assistant', 'Could not pin the note. Try saving from the Coach setup tab.');
          }
        });
    }

    function handleAnswerResponse(data) {
      var ans = (data && data.answer) ? data.answer : '';
      if (!ans.trim()) {
        ans = 'I could not build an answer for that. Try a shorter question or tap **Risk:Reward**.';
      }
      appendChat('assistant', ans, { usedWeb: !!(data && data.used_web) });
      renderFollowUps((data && data.follow_ups) ? data.follow_ups : []);
      if (data && data.suggested_weekly_focus) showSuggestedFocus(data.suggested_weekly_focus);
      if (coachActive) {
        speakText(ans).then(function () {
          if (coachActive && !requestInFlight) startListening();
        });
      }
    }

    function onAskClick(forcedQuestion) {
      if (requestInFlight) return;
      var questionEl = document.getElementById('aiQuestion');
      if (!questionEl) return;
      var q = (forcedQuestion || questionEl.value || '').trim();
      if (!q) {
        setCoachStatus('idle', 'Type your question first, or tap a quick chip below.');
        if (questionEl) questionEl.focus();
        return;
      }

      ensureChatTab();
      clearVoiceSendTimer();
      questionEl.classList.remove('tv-voice-interim', 'tv-voice-listening');
      questionEl.value = '';
      appendChat('user', q);
      var priorHistory = HISTORY.slice(0, -1);

      requestInFlight = true;
      setChatBusy(true, q);

      fetch(AI_QUERY_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'X-CSRFToken': CSRF,
          'X-CSRF-Token': CSRF,
        },
        body: JSON.stringify({ question: q, history: priorHistory }),
      })
        .then(function (r) {
          if (!r.ok) {
            return r.json().catch(function () { return {}; }).then(function (err) {
              throw new Error((err && err.answer) || ('HTTP ' + r.status));
            });
          }
          return r.json();
        })
        .then(function (data) {
          handleAnswerResponse(data);
        })
        .catch(function (err) {
          var msg = (err && err.message) ? String(err.message) : '';
          if (msg.indexOf('HTTP 503') >= 0) {
            appendChat('assistant', 'AI Coach is temporarily unavailable. Your local coach will be back shortly — try again in a moment.');
          } else {
            appendChat('assistant', 'I could not reach the coach right now. Check your connection and try again, or rephrase in one short sentence.');
          }
        })
        .finally(function () {
          requestInFlight = false;
          setChatBusy(false);
        });
    }

    function runTradeDoctor() {
      if (requestInFlight) return;
      ensureChatTab();
      appendChat('assistant', '**Trade Doctor** is analyzing your last 10 closed trades…');
      requestInFlight = true;
      setChatBusy(true);
      fetch(TRADE_DOCTOR_URL, { headers: { Accept: 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          lastTradeDoctor = d;
          var text = (d && d.text) ? d.text : 'Log at least 3 closed trades with strategy, emotion, and stop loss — then run Trade Doctor again.';
          appendChat('assistant', text);
          if (d && d.leak && d.leak !== 'No recent closed trades') {
            var actions = document.createElement('div');
            actions.className = 'd-flex flex-wrap gap-2 mt-2';
            var pinBtn = document.createElement('button');
            pinBtn.type = 'button';
            pinBtn.className = 'btn btn-sm btn-primary';
            pinBtn.textContent = 'Pin this plan';
            pinBtn.addEventListener('click', function () { pinTradeDoctor(d); });
            var focusBtn = document.createElement('button');
            focusBtn.type = 'button';
            focusBtn.className = 'btn btn-sm btn-outline-primary';
            focusBtn.textContent = 'Use as weekly focus';
            focusBtn.addEventListener('click', function () {
              var rule = (d.suggested_focus || ('Trade Doctor: ' + d.leak) || '').trim();
              applyWeeklyFocus(rule);
              if (rule) showSuggestedFocus(rule);
            });
            var labBtn = document.createElement('a');
            labBtn.className = 'btn btn-sm btn-outline-secondary';
            labBtn.textContent = 'Stress-test in Lab';
            var labPrompt = 'Only take setups that avoid this leak: ' + d.leak +
              '. Require a stop at invalidation, planned R:R at least 1.5, and skip revenge entries after a loss.';
            labBtn.href = '/lab/?description=' + encodeURIComponent(labPrompt) + '&mode=journal&from=ai';
            actions.appendChild(pinBtn);
            actions.appendChild(focusBtn);
            actions.appendChild(labBtn);
            var log = document.getElementById('aiChatLog');
            if (log && log.lastChild) log.lastChild.appendChild(actions);
            if (d.suggested_focus) showSuggestedFocus(d.suggested_focus);
            if (d.compliance && d.compliance.sample_size) {
              appendChat(
                'assistant',
                '**Focus adherence:** ' + (d.compliance.label || '') + ' — ' + (d.compliance.detail || '')
              );
            }
          }
        })
        .catch(function () {
          appendChat('assistant', 'Trade Doctor could not load right now. Try again in a moment.');
        })
        .finally(function () {
          requestInFlight = false;
          setChatBusy(false);
        });
    }

    function startListening() {
      if (!coachActive || requestInFlight || isSpeaking) return;
      var SR = global.SpeechRecognition || global.webkitSpeechRecognition;
      if (!SR) return;
      try {
        if (!recognition) {
          recognition = new SR();
          recognition.lang = 'en-US';
          recognition.interimResults = true;
          recognition.continuous = false;
          recognition.maxAlternatives = 1;
          recognition.onresult = function (evt) {
            if (!coachActive || requestInFlight) return;
            var parsed = extractTranscript(evt);
            if (!parsed.text) return;
            var qEl = document.getElementById('aiQuestion');
            if (qEl) {
              qEl.value = parsed.text;
              qEl.classList.toggle('tv-voice-interim', !parsed.isFinal);
              qEl.classList.add('tv-voice-listening');
            }
            setTalkTranscript(parsed.text, !parsed.isFinal);
            if (parsed.isFinal) {
              setCoachStatus('listening', 'Got it — processing…');
              stopListening();
              scheduleVoiceSend(parsed.text);
            } else {
              setCoachStatus('listening', 'Listening…');
            }
          };
          recognition.onerror = function (ev) {
            var code = (ev && ev.error) ? ev.error : 'unknown';
            if (code === 'aborted' || code === 'no-speech') return;
            setCoachStatus('error', 'Voice issue: ' + code + '. Type your question or try again.');
            if (coachActive) {
              appendChat('assistant', 'Voice input issue (' + code + '). You can type your question instead.', { skipHistory: false });
            }
          };
          recognition.onend = function () {
            isListening = false;
            var qEl = document.getElementById('aiQuestion');
            if (qEl) qEl.classList.remove('tv-voice-listening');
            if (!isVoiceAutoSend() && coachActive && !requestInFlight && !isSpeaking) return;
            if (coachActive && !requestInFlight && !isSpeaking && !voiceSendTimer) {
              setTimeout(function () {
                try {
                  if (coachActive && !requestInFlight && !isSpeaking && !voiceSendTimer) startListening();
                } catch (e) {}
              }, 600);
            }
          };
        }
        isListening = true;
        var qEl = document.getElementById('aiQuestion');
        if (qEl) qEl.classList.add('tv-voice-listening');
        setCoachStatus('listening', 'Listening… speak clearly.');
        recognition.start();
      } catch (e) {}
    }

    function stopCoach() {
      coachActive = false;
      clearVoiceSendTimer();
      var stopBtn = document.getElementById('coachStopBtn');
      var coachBtn = document.getElementById('coachTalkBtn');
      if (stopBtn) stopBtn.classList.add('d-none');
      if (coachBtn) {
        coachBtn.disabled = false;
        coachBtn.classList.remove('tv-coach-active', 'tv-speaking');
      }
      stopListening();
      stopWaveform();
      stopNeuralAudio();
      setTalkOverlayOpen(false);
      try { global.speechSynthesis.cancel(); } catch (e) {}
      isSpeaking = false;
      setCoachStatus('idle', 'Pick an action above, or type a question below.');
    }

    function startCoach() {
      ensureChatTab();
      coachActive = true;
      var stopBtn = document.getElementById('coachStopBtn');
      var coachBtn = document.getElementById('coachTalkBtn');
      if (stopBtn) stopBtn.classList.remove('d-none');
      if (coachBtn) {
        coachBtn.disabled = true;
        coachBtn.classList.add('tv-coach-active');
      }
      setTalkOverlayOpen(true);
      setTalkVisualState('listening');
      setTalkTranscript('Start talking — I’ll show your words here.', true);
      startWaveform();
      var intro = USERNAME
        ? USERNAME + ', I’m listening. Ask out loud — I’ll answer, then listen again.'
        : 'I’m listening. Ask out loud — I’ll answer, then listen again.';
      if (!coachIntroShown) {
        coachIntroShown = true;
        setCoachStatus('speaking', 'Starting Talk mode…');
        setTalkVisualState('speaking');
        appendChat('assistant', intro, { skipStore: false });
        speakText(intro).then(startListening);
      } else {
        setCoachStatus('listening', 'Listening… speak your question.');
        startListening();
      }
    }

    var voiceBtn = document.getElementById('voiceBtn');
    var voicePauseBtn = document.getElementById('voicePauseBtn');
    var voiceStopBtn = document.getElementById('voiceStopBtn');
    var submitBtn = document.getElementById('aiSubmitBtn');
    var clearBtn = document.getElementById('aiClearBtn');
    var questionEl = document.getElementById('aiQuestion');
    var coachBtn = document.getElementById('coachTalkBtn');
    var stopBtn = document.getElementById('coachStopBtn');
    var quickWrap = document.getElementById('aiQuickChips');
    var followWrap = document.getElementById('aiFollowUps');
    var tdBtn = document.getElementById('tradeDoctorBtn');
    var useFocusBtn = document.getElementById('useSuggestedFocusBtn');
    var suggestFocusBtn = document.getElementById('suggestFocusBtn');

    if (voiceBtn) voiceBtn.addEventListener('click', playVoiceReview);
    if (voicePauseBtn) voicePauseBtn.addEventListener('click', function () {
      if (!global.speechSynthesis) return;
      if (global.speechSynthesis.paused) global.speechSynthesis.resume();
      else global.speechSynthesis.pause();
    });
    if (voiceStopBtn) voiceStopBtn.addEventListener('click', function () {
      try { global.speechSynthesis.cancel(); } catch (e) {}
      isSpeaking = false;
    });
    if (submitBtn) submitBtn.addEventListener('click', function () { onAskClick(); });
    if (clearBtn) clearBtn.addEventListener('click', function () {
      HISTORY = [];
      requestInFlight = false;
      try { sessionStorage.removeItem('tv_ai_history'); } catch (e) {}
      renderFollowUps([]);
      var log = document.getElementById('aiChatLog');
      if (log) log.textContent = '';
      updateEmptyHints();
      ensureChatTab();
      clearVoiceSendTimer();
      if (questionEl) {
        questionEl.value = '';
        questionEl.classList.remove('tv-voice-interim', 'tv-voice-listening');
        questionEl.focus();
        questionEl.placeholder = 'Message your coach…';
      }
      if (!coachActive) {
        setCoachStatus('idle', 'Type a question, or tap Talk to speak with your coach.');
      }
    });
    if (questionEl) questionEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        onAskClick();
      }
    });
    if (tdBtn) tdBtn.addEventListener('click', runTradeDoctor);

    var narrativeFocusBtn = document.getElementById('narrativeFocusBtn');
    var narrativeDoctorBtn = document.getElementById('narrativeDoctorBtn');
    var firstWinDoctorBtn = document.getElementById('firstWinDoctorBtn');
    if (narrativeFocusBtn) {
      narrativeFocusBtn.addEventListener('click', function () {
        var rule = (narrativeFocusBtn.getAttribute('data-rule') || '').trim();
        if (!rule) return;
        applyWeeklyFocus(rule);
        showSuggestedFocus(rule);
        ensureChatTab();
      });
    }
    if (narrativeDoctorBtn) {
      narrativeDoctorBtn.addEventListener('click', function () {
        ensureChatTab();
        runTradeDoctor();
      });
    }
    if (firstWinDoctorBtn) {
      firstWinDoctorBtn.addEventListener('click', function () {
        ensureChatTab();
        runTradeDoctor();
      });
    }

    if (coachBtn) coachBtn.addEventListener('click', function () {
      var SR = global.SpeechRecognition || global.webkitSpeechRecognition;
      if (!SR) {
        appendChat('assistant', 'Talk mode is not supported in this browser. Use typed chat or Play Voice Review.');
        return;
      }
      startCoach();
    });
    if (stopBtn) stopBtn.addEventListener('click', stopCoach);
    var talkEndBtn = document.getElementById('tvTalkEndBtn');
    if (talkEndBtn) talkEndBtn.addEventListener('click', stopCoach);

    bindVoiceSelect(document.getElementById('aiVoiceSelect'));
    bindVoiceSelect(document.getElementById('aiVoiceSelectComposer'));
    populateVoiceSelects();
    if (global.speechSynthesis) {
      global.speechSynthesis.onvoiceschanged = populateVoiceSelects;
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && coachActive) stopCoach();
    });

    function handleChipClick(e) {
      var t = e.target;
      var q = t && t.getAttribute && t.getAttribute('data-q');
      if (q) onAskClick(q);
    }
    if (quickWrap) quickWrap.addEventListener('click', handleChipClick);
    if (followWrap) followWrap.addEventListener('click', handleChipClick);

    if (useFocusBtn) useFocusBtn.addEventListener('click', function () {
      var txt = document.getElementById('aiSuggestedFocusText');
      applyWeeklyFocus(txt ? txt.textContent : '');
    });
    if (suggestFocusBtn) suggestFocusBtn.addEventListener('click', function () {
      onAskClick('Suggest a weekly focus rule for me based on my trading.');
    });

    function runTodaysReview() {
      ensureChatTab();
      if (requestInFlight) return;
      appendChat('assistant', 'Pulling today’s review from your journal…', { skipHistory: true });
      var url = BRIEFING_URL || '/dashboard/ai/briefing';
      fetch(url, { headers: { Accept: 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var lines = (d && d.lines) ? d.lines : [];
          var text = lines.length
            ? lines.join('\n\n')
            : (VOICE_TEXT || 'Quiet day so far — close a trade and I’ll brief you.');
          appendChat('assistant', text);
          speakText(text);
        })
        .catch(function () {
          appendChat('assistant', VOICE_TEXT || 'Could not load today’s review. Try Ask the Coach.');
        });
    }

    var actionTalk = document.getElementById('coachActionTalk');
    var actionToday = document.getElementById('coachActionToday');
    var actionLeaks = document.getElementById('coachActionLeaks');
    var actionAsk = document.getElementById('coachActionAsk');
    if (actionTalk) actionTalk.addEventListener('click', function () {
      if (coachBtn) coachBtn.click();
    });
    if (actionToday) actionToday.addEventListener('click', runTodaysReview);
    if (actionLeaks) actionLeaks.addEventListener('click', function () { runTradeDoctor(); });
    if (actionAsk) actionAsk.addEventListener('click', function () { ensureChatTab(); });
    document.querySelectorAll('.tv-card-leaks').forEach(function (b) {
      b.addEventListener('click', function () { runTradeDoctor(); });
    });
    document.querySelectorAll('.tv-card-ask').forEach(function (b) {
      b.addEventListener('click', function () { ensureChatTab(); });
    });

    var GOALS_URL = root.getAttribute('data-goals-url') || '';
    var CHALLENGES_URL = root.getAttribute('data-challenges-url') || '';

    document.querySelectorAll('.tv-goal-quick').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (!GOALS_URL) return;
        var title = btn.getAttribute('data-title') || 'Goal';
        var metric = btn.getAttribute('data-metric') || 'custom';
        var target = parseFloat(btn.getAttribute('data-target') || '0') || null;
        fetch(GOALS_URL, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': CSRF,
            'X-CSRF-Token': CSRF,
          },
          body: JSON.stringify({ title: title, metric: metric, target_value: target, target_text: title, days: 30 }),
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d && d.ok) {
              appendChat('assistant', 'Goal saved: **' + title + '**. ' + ((d.goal && d.goal.progress_detail) || 'I’ll track this from your journal.'));
              setTimeout(function () { window.location.reload(); }, 800);
            } else {
              appendChat('assistant', 'Could not save that goal right now.');
            }
          })
          .catch(function () {
            appendChat('assistant', 'Could not save that goal right now.');
          });
      });
    });

    document.querySelectorAll('.tv-challenge-start').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (!CHALLENGES_URL) return;
        var code = btn.getAttribute('data-code');
        if (!code) return;
        fetch(CHALLENGES_URL, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': CSRF,
            'X-CSRF-Token': CSRF,
          },
          body: JSON.stringify({ code: code }),
        })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d && d.ok && d.challenge) {
              appendChat(
                'assistant',
                'Challenge started: **' + d.challenge.title + '**. ' +
                  (d.challenge.progress_detail || 'I’ll track progress from your next closed trades.')
              );
              setTimeout(function () { window.location.reload(); }, 900);
            } else {
              appendChat('assistant', (d && d.error) || 'Could not start that challenge.');
            }
          })
          .catch(function () {
            appendChat('assistant', 'Could not start that challenge right now.');
          });
      });
    });

    refreshBasis();
    setInterval(refreshBasis, 60000);

    try {
      var saved = sessionStorage.getItem('tv_ai_history');
      if (saved) {
        var parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          HISTORY = parsed.slice(-14);
          for (var i = 0; i < HISTORY.length; i++) {
            var m = HISTORY[i];
            if (m && m.role && m.content) appendChat(m.role, m.content, { skipHistory: true, skipStore: true });
          }
          updateEmptyHints();
        }
      }
    } catch (e) {}

    var initialFocus = root.getAttribute('data-suggested-focus');
    if (initialFocus) showSuggestedFocus(initialFocus);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAiBuddyPage);
  } else {
    initAiBuddyPage();
  }
})(typeof window !== 'undefined' ? window : this);
