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
      var panels = {
        today: document.getElementById('ai-section-today'),
        review: document.getElementById('ai-section-review'),
        setup: document.getElementById('ai-section-setup'),
      };
      Object.keys(panels).forEach(function (key) {
        var el = panels[key];
        if (!el) return;
        if (key === name) el.classList.remove('d-none');
        else el.classList.add('d-none');
      });
      document.querySelectorAll('#aiBuddyTabs [data-ai-tab]').forEach(function (btn) {
        var active = btn.getAttribute('data-ai-tab') === name;
        btn.classList.toggle('active', active);
      });
      try { sessionStorage.setItem('tv_ai_tab', name); } catch (e) {}
    }

    function ensureChatTab() {
      showAiTab('today');
      var card = document.getElementById('ai-chat-card');
      if (card && card.scrollIntoView) {
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }

    function scrollChatToBottom() {
      var log = document.getElementById('aiChatLog');
      if (log) log.scrollTop = log.scrollHeight;
    }

    var VOICE_PREF_KEY = 'tv_ai_buddy_voice';
    var cachedVoice = null;
    var speakGeneration = 0;

    /** Score browser voices — prefer neural / natural names over compact robotic ones. */
    function scoreVoice(v) {
      if (!v) return -1000;
      var name = String(v.name || '').toLowerCase();
      var lang = String(v.lang || '').toLowerCase();
      if (lang.indexOf('en') !== 0) return -500;

      var score = 10;
      // Strong preference: modern neural / natural voices
      if (/neural|natural|premium|enhanced|wavenet|studio|online \(natural\)/.test(name)) score += 120;
      if (/google/.test(name) && /us|uk|gb|au/.test(lang)) score += 90;
      if (/microsoft/.test(name) && /(aria|jenny|guy|sara|sonia|natasha|ryan|davis|jane|jason)/.test(name)) score += 100;
      if (/microsoft/.test(name) && /natural/.test(name)) score += 80;
      // Classic high-quality system voices
      if (/(samantha|karen|moira|daniel|alex|victoria|oliver|ava|zoe|allison|susan|tom|fred)/.test(name)) score += 70;
      if (/siri|premium/.test(name)) score += 60;
      // Mild preference for US/GB English (most coach-like)
      if (lang === 'en-us' || lang.indexOf('en-us') === 0) score += 25;
      if (lang === 'en-gb' || lang.indexOf('en-gb') === 0) score += 20;
      if (v.localService === false) score += 15; // often cloud neural on Chromium
      // Penalize known robotic / novelty voices
      if (/(compact|espeak|robot|whisper|zarvox|trinoids|bad news|good news|bubbles|boing|bells|cellos|pipe organ)/.test(name)) score -= 200;
      if (/(dummy|silent)/.test(name)) score -= 300;
      return score;
    }

    function listEnglishVoices() {
      try {
        var voices = global.speechSynthesis ? global.speechSynthesis.getVoices() : [];
        return voices
          .filter(function (v) { return (v.lang || '').toLowerCase().indexOf('en') === 0; })
          .slice()
          .sort(function (a, b) { return scoreVoice(b) - scoreVoice(a); });
      } catch (e) {
        return [];
      }
    }

    function pickEnglishVoice(preferredName) {
      try {
        var voices = listEnglishVoices();
        if (!voices.length) return null;
        var want = (preferredName || '').trim();
        if (!want) {
          try { want = localStorage.getItem(VOICE_PREF_KEY) || ''; } catch (e) { want = ''; }
        }
        if (want) {
          for (var i = 0; i < voices.length; i++) {
            if (voices[i].name === want) return voices[i];
          }
        }
        return voices[0];
      } catch (e) {}
      return null;
    }

    function refreshVoicePicker() {
      var sel = document.getElementById('aiVoiceSelect');
      if (!sel || !global.speechSynthesis) return;
      var voices = listEnglishVoices();
      var saved = '';
      try { saved = localStorage.getItem(VOICE_PREF_KEY) || ''; } catch (e) {}
      var best = pickEnglishVoice(saved);
      var prev = sel.value;
      sel.textContent = '';
      if (!voices.length) {
        var empty = document.createElement('option');
        empty.value = '';
        empty.textContent = 'Default browser voice';
        sel.appendChild(empty);
        return;
      }
      for (var i = 0; i < voices.length; i++) {
        var v = voices[i];
        var opt = document.createElement('option');
        opt.value = v.name;
        var tag = scoreVoice(v) >= 80 ? ' · natural' : '';
        opt.textContent = v.name + ' (' + (v.lang || 'en') + ')' + tag;
        sel.appendChild(opt);
      }
      var pick = saved || (best && best.name) || prev || voices[0].name;
      sel.value = pick;
      if (sel.value !== pick && best) sel.value = best.name;
      cachedVoice = pickEnglishVoice(sel.value);
    }

    function bindVoicePicker() {
      var sel = document.getElementById('aiVoiceSelect');
      if (!sel) return;
      sel.addEventListener('change', function () {
        try { localStorage.setItem(VOICE_PREF_KEY, sel.value || ''); } catch (e) {}
        cachedVoice = pickEnglishVoice(sel.value);
        // Short sample so the trader hears the chosen coach voice
        speakText("Hey — this is your TradeVerse coach. I'll keep it clear and natural.", { sample: true });
      });
      refreshVoicePicker();
      if (global.speechSynthesis) {
        global.speechSynthesis.onvoiceschanged = function () {
          refreshVoicePicker();
        };
        // Some browsers load voices asynchronously after a tick
        setTimeout(refreshVoicePicker, 250);
        setTimeout(refreshVoicePicker, 1000);
      }
    }

    /** Turn chat/markdown copy into something that sounds natural when spoken. */
    function cleanForSpeech(text) {
      var s = String(text || '');
      s = s.replace(/\*\*/g, '').replace(/\*/g, '');
      s = s.replace(/`+/g, '');
      s = s.replace(/#{1,6}\s*/g, '');
      s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
      s = s.replace(/^\s*[-•]\s+/gm, '');
      s = s.replace(/\bR\s*[:/]\s*R\b/gi, 'risk to reward');
      s = s.replace(/\bR:R\b/g, 'risk to reward');
      s = s.replace(/\bP\s*[/&]\s*L\b/gi, 'P and L');
      s = s.replace(/\bPnL\b/gi, 'P and L');
      s = s.replace(/\bSL\b/g, 'stop loss');
      s = s.replace(/\bTP\b/g, 'take profit');
      s = s.replace(/\bWR\b/g, 'win rate');
      s = s.replace(/\bFOMO\b/g, 'FOMO');
      s = s.replace(/(\d+)%/g, '$1 percent');
      s = s.replace(/—|–/g, ', ');
      s = s.replace(/\s*\n+\s*/g, '. ');
      s = s.replace(/\s{2,}/g, ' ');
      s = s.replace(/\.{2,}/g, '.');
      s = s.replace(/\s+([,.!?])/g, '$1');
      return s.trim();
    }

    function splitSentences(text) {
      var plain = cleanForSpeech(text);
      if (!plain) return [];
      // Prefer sentence boundaries; fall back to clauses for long run-ons
      var parts = plain.split(/(?<=[.!?])\s+/).map(function (s) { return s.trim(); }).filter(Boolean);
      var out = [];
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i];
        if (p.length > 180) {
          var clauses = p.split(/(?<=[,;:])\s+/).map(function (c) { return c.trim(); }).filter(Boolean);
          if (clauses.length > 1) {
            out = out.concat(clauses);
            continue;
          }
        }
        out.push(p);
      }
      return out;
    }

    function pause(ms) {
      return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    function setCoachStatus(state, message) {
      var el = document.getElementById('aiCoachStatus');
      if (!el) return;
      el.classList.remove('is-listening', 'is-thinking', 'is-speaking', 'is-error');
      if (state === 'listening') el.classList.add('is-listening');
      else if (state === 'thinking') el.classList.add('is-thinking');
      else if (state === 'speaking') el.classList.add('is-speaking');
      else if (state === 'error') el.classList.add('is-error');
      if (message) el.textContent = message;
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
      if (!isVoiceAutoSend()) {
        setCoachStatus('idle', 'Review your question in the box, then tap Ask AI Buddy.');
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

    function speakChunk(text, opts) {
      opts = opts || {};
      return new Promise(function (resolve) {
        if (!global.speechSynthesis) { resolve(); return; }
        var plain = cleanForSpeech(text);
        if (!plain) { resolve(); return; }
        var u = new SpeechSynthesisUtterance(plain);
        // Slightly under 1.0 reads warmer; tiny pitch lift avoids flat robot tone
        u.rate = typeof opts.rate === 'number' ? opts.rate : 0.96;
        u.pitch = typeof opts.pitch === 'number' ? opts.pitch : 1.02;
        u.volume = 1;
        var v = cachedVoice || pickEnglishVoice();
        cachedVoice = v;
        if (v) {
          u.voice = v;
          u.lang = v.lang || 'en-US';
        } else {
          u.lang = 'en-US';
        }
        var settled = false;
        function done() {
          if (settled) return;
          settled = true;
          resolve();
        }
        u.onend = done;
        u.onerror = done;
        try {
          global.speechSynthesis.speak(u);
        } catch (e) {
          done();
        }
      });
    }

    function finishSpeakingUi() {
      isSpeaking = false;
      var coachBtn = document.getElementById('coachTalkBtn');
      if (coachBtn) coachBtn.classList.remove('tv-speaking');
      if (coachActive && !requestInFlight) {
        setCoachStatus('listening', 'Listening… speak your next question.');
      } else if (!coachActive) {
        setCoachStatus('idle', 'Type a question or tap Coach Talk to use your microphone.');
      }
    }

    /**
     * Speak naturally: clean copy, prefer neural voices, pause between sentences.
     * opts.sample — short preview (skips coach listen-loop UI resets lightly)
     * opts.single — force one utterance (rarely needed)
     */
    async function speakText(text, opts) {
      opts = opts || {};
      if (!global.speechSynthesis) return;
      stopListening();
      speakGeneration += 1;
      var gen = speakGeneration;
      try { global.speechSynthesis.cancel(); } catch (e) {}
      // Chromium sometimes needs a tick after cancel before the next utterance
      await pause(40);
      if (gen !== speakGeneration) return;

      var queue = opts.single ? [cleanForSpeech(text)].filter(Boolean) : splitSentences(text);
      if (!queue.length) return;

      isSpeaking = true;
      setCoachStatus('speaking', opts.sample ? 'Previewing coach voice…' : 'Speaking…');
      var coachBtn = document.getElementById('coachTalkBtn');
      if (coachBtn && !opts.sample) coachBtn.classList.add('tv-speaking');

      try {
        for (var i = 0; i < queue.length; i++) {
          if (gen !== speakGeneration) break;
          await speakChunk(queue[i], opts);
          if (gen !== speakGeneration) break;
          // Natural breath between sentences (longer after questions)
          var gap = /[?]$/.test(queue[i]) ? 280 : (/[!]$/.test(queue[i]) ? 220 : 160);
          if (i < queue.length - 1) await pause(gap);
        }
      } finally {
        if (gen === speakGeneration) finishSpeakingUi();
      }
    }

    function stopSpeaking() {
      speakGeneration += 1;
      try { global.speechSynthesis.cancel(); } catch (e) {}
      finishSpeakingUi();
    }

    async function playVoiceReview() {
      if (!VOICE_TEXT || !global.speechSynthesis) return;
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
      bubble.className = 'tv-surface soft p-3 mb-2';
      var head = document.createElement('div');
      head.className = 'd-flex align-items-center justify-content-between gap-2 small tv-muted mb-2';
      var who = document.createElement('div');
      who.textContent = role === 'user' ? (USERNAME ? USERNAME + ' (you)' : 'You') : 'AI Buddy';
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
          : '<div class="small tv-muted mb-1">AI Buddy</div>';
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
      } else if (!coachActive) {
        setCoachStatus('idle', 'Type a question or tap Coach Talk to use your microphone.');
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
            var msg = 'Saved your weekly focus: **' + rule + '**. AI Buddy will score the next trades against this rule.';
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
            appendChat('assistant', 'AI Buddy is temporarily unavailable. Your local coach will be back shortly — try again in a moment.');
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
            if (parsed.isFinal) {
              setCoachStatus('listening', 'Got it — processing…');
              stopListening();
              scheduleVoiceSend(parsed.text);
            } else {
              setCoachStatus('listening', 'Listening… ' + parsed.text);
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
      stopSpeaking();
      setCoachStatus('idle', 'Type a question or tap Coach Talk to use your microphone.');
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
      var intro = USERNAME
        ? 'Hey ' + USERNAME + '. Ask out loud — I\'ll answer, then listen again.'
        : 'Hey — ask out loud. I\'ll answer, then listen again.';
      if (!coachIntroShown) {
        coachIntroShown = true;
        setCoachStatus('speaking', 'Starting Coach Talk…');
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
      stopSpeaking();
    });
    if (submitBtn) submitBtn.addEventListener('click', function () { onAskClick(); });
    if (clearBtn) clearBtn.addEventListener('click', function () {
      HISTORY = [];
      requestInFlight = false;
      try { sessionStorage.removeItem('tv_ai_history'); } catch (e) {}
      renderFollowUps([]);
      var log = document.getElementById('aiChatLog');
      if (log) log.textContent = '';
      ensureChatTab();
      clearVoiceSendTimer();
      if (questionEl) {
        questionEl.value = '';
        questionEl.classList.remove('tv-voice-interim', 'tv-voice-listening');
        questionEl.focus();
        questionEl.placeholder = 'Ask a trading question…';
      }
      if (!coachActive) {
        setCoachStatus('idle', 'Type a question or tap Coach Talk to use your microphone.');
      }
    });
    if (questionEl) questionEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') onAskClick();
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
        appendChat('assistant', 'Coach Talk is not supported in this browser. Use typed chat or Play Voice Review.');
        return;
      }
      startCoach();
    });
    if (stopBtn) stopBtn.addEventListener('click', stopCoach);

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

    bindVoicePicker();
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
        }
      }
    } catch (e) {}

    var initialFocus = root.getAttribute('data-suggested-focus');
    if (initialFocus) showSuggestedFocus(initialFocus);

    var savedTab = 'today';
    try { savedTab = sessionStorage.getItem('tv_ai_tab') || 'today'; } catch (e) {}
    if (['today', 'review', 'setup'].indexOf(savedTab) < 0) savedTab = 'today';
    showAiTab(savedTab);

    document.querySelectorAll('#aiBuddyTabs [data-ai-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tab = btn.getAttribute('data-ai-tab');
        if (tab) showAiTab(tab);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAiBuddyPage);
  } else {
    initAiBuddyPage();
  }
})(typeof window !== 'undefined' ? window : this);
