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
    var recognition = null;
    var isSpeaking = false;
    var coachAutoSend = true;
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

    function pickEnglishVoice() {
      try {
        var voices = global.speechSynthesis ? global.speechSynthesis.getVoices() : [];
        for (var i = 0; i < voices.length; i++) {
          if ((voices[i].lang || '').toLowerCase().indexOf('en') === 0) return voices[i];
        }
      } catch (e) {}
      return null;
    }

    function speakText(text) {
      return new Promise(function (resolve) {
        if (!global.speechSynthesis) { resolve(); return; }
        try { if (recognition) recognition.stop(); } catch (e) {}
        global.speechSynthesis.cancel();
        var u = new SpeechSynthesisUtterance(text);
        u.rate = 1.02;
        u.pitch = 1.03;
        var v = pickEnglishVoice();
        if (v) u.voice = v;
        isSpeaking = true;
        var coachBtn = document.getElementById('coachTalkBtn');
        if (coachBtn) coachBtn.classList.add('tv-speaking');
        u.onend = u.onerror = function () {
          isSpeaking = false;
          if (coachBtn) coachBtn.classList.remove('tv-speaking');
          resolve();
        };
        global.speechSynthesis.speak(u);
      });
    }

    function splitSentences(text) {
      return String(text || '').replace(/\s+/g, ' ').split(/(?<=[.!?])\s+/).map(function (s) { return s.trim(); }).filter(Boolean);
    }

    async function playVoiceReview() {
      if (!VOICE_TEXT || !global.speechSynthesis) return;
      var queue = splitSentences(VOICE_TEXT);
      for (var i = 0; i < queue.length; i++) {
        await speakText(queue[i]);
      }
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
      if (!opts.skipHistory) {
        HISTORY.push({ role: role, content: content });
        if (HISTORY.length > 14) HISTORY = HISTORY.slice(-14);
      }
      if (!opts.skipStore) {
        try { sessionStorage.setItem('tv_ai_history', JSON.stringify(HISTORY)); } catch (e) {}
      }
    }

    function setLoading(isLoading) {
      var btn = document.getElementById('aiSubmitBtn');
      if (btn) {
        btn.disabled = !!isLoading;
        btn.classList.toggle('loading', !!isLoading);
      }
      var q = document.getElementById('aiQuestion');
      if (q) q.disabled = !!isLoading;
      var log = document.getElementById('aiChatLog');
      var existing = document.getElementById('aiTyping');
      if (isLoading && log && !existing) {
        var bubble = document.createElement('div');
        bubble.id = 'aiTyping';
        bubble.className = 'tv-surface soft p-3 mb-2';
        bubble.innerHTML = '<div class="small tv-muted mb-1">AI Buddy</div><div class="tv-typing" aria-label="Thinking"><span></span><span></span><span></span></div>';
        log.appendChild(bubble);
      } else if (!isLoading && existing) {
        existing.remove();
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
            appendChat('assistant', 'Saved your weekly focus: **' + rule + '**');
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

    function onAskClick(forcedQuestion) {
      var questionEl = document.getElementById('aiQuestion');
      if (!questionEl) return;
      var q = (forcedQuestion || questionEl.value || '').trim();
      if (!q) return;
      questionEl.value = '';
      appendChat('user', q);
      setLoading(true);
      var xhr = new XMLHttpRequest();
      xhr.open('POST', AI_QUERY_URL, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('X-CSRFToken', CSRF);
      xhr.setRequestHeader('X-CSRF-Token', CSRF);
      xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4) return;
        setLoading(false);
        if (xhr.status === 200) {
          try {
            var data = JSON.parse(xhr.responseText);
            var ans = (data && data.answer) ? data.answer : 'Sorry, AI Buddy could not answer that right now.';
            appendChat('assistant', ans);
            renderFollowUps((data && data.follow_ups) ? data.follow_ups : []);
            if (data && data.suggested_weekly_focus) showSuggestedFocus(data.suggested_weekly_focus);
            if (coachActive) {
              speakText(ans).then(function () { startListening(); });
            }
          } catch (e) {
            appendChat('assistant', 'Sorry, AI Buddy could not answer that right now.');
          }
        } else {
          appendChat('assistant', 'Unable to reach AI Buddy. Please try again later.');
        }
      };
      xhr.onerror = function () {
        setLoading(false);
        appendChat('assistant', 'Unable to reach AI Buddy. Please try again later.');
      };
      xhr.send(JSON.stringify({ question: q, history: HISTORY }));
    }

    function runTradeDoctor() {
      appendChat('assistant', '**Trade Doctor** is analyzing your last 10 closed trades…');
      setLoading(true);
      fetch(TRADE_DOCTOR_URL, { headers: { Accept: 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          lastTradeDoctor = d;
          var text = (d && d.text) ? d.text : 'Trade Doctor returned no analysis.';
          appendChat('assistant', text);
          if (d && d.leak) {
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
              var rule = 'Trade Doctor: ' + d.leak;
              applyWeeklyFocus(rule);
            });
            actions.appendChild(pinBtn);
            actions.appendChild(focusBtn);
            var log = document.getElementById('aiChatLog');
            if (log && log.lastChild) log.lastChild.appendChild(actions);
          }
        })
        .catch(function () {
          appendChat('assistant', 'Trade Doctor couldn’t load right now. Try again in a moment.');
        })
        .finally(function () { setLoading(false); });
    }

    function startListening() {
      if (!coachActive) return;
      var SR = global.SpeechRecognition || global.webkitSpeechRecognition;
      if (!SR) return;
      try {
        if (!recognition) {
          recognition = new SR();
          recognition.lang = 'en-US';
          recognition.interimResults = false;
          recognition.maxAlternatives = 1;
          recognition.onresult = function (evt) {
            var res = evt.results && evt.results[0] && evt.results[0][0] ? evt.results[0][0] : null;
            var transcript = res ? (res.transcript || '').trim() : '';
            var questionEl = document.getElementById('aiQuestion');
            if (questionEl && transcript) {
              questionEl.value = transcript;
              appendChat('assistant', 'I heard: “' + transcript + '”' + (coachAutoSend ? ' — sending…' : ' — tap Ask when ready.'));
              if (coachAutoSend) {
                setTimeout(function () { onAskClick(transcript); }, 400);
              }
            }
          };
          recognition.onerror = function (ev) {
            var code = (ev && ev.error) ? ev.error : 'unknown';
            if (code !== 'aborted' && code !== 'no-speech') {
              appendChat('assistant', 'Voice input issue (' + code + '). You can type your question instead.');
            }
          };
          recognition.onend = function () {
            if (coachActive && !isSpeaking) {
              setTimeout(function () { try { recognition.start(); } catch (e) {} }, 500);
            }
          };
        }
        if (!isSpeaking) recognition.start();
      } catch (e) {}
    }

    function stopCoach() {
      coachActive = false;
      var stopBtn = document.getElementById('coachStopBtn');
      var coachBtn = document.getElementById('coachTalkBtn');
      if (stopBtn) stopBtn.classList.add('d-none');
      if (coachBtn) coachBtn.disabled = false;
      try { if (recognition) recognition.stop(); } catch (e) {}
      try { global.speechSynthesis.cancel(); } catch (e) {}
    }

    function startCoach() {
      coachActive = true;
      var stopBtn = document.getElementById('coachStopBtn');
      var coachBtn = document.getElementById('coachTalkBtn');
      if (stopBtn) stopBtn.classList.remove('d-none');
      if (coachBtn) coachBtn.disabled = true;
      var intro = USERNAME
        ? 'Hey ' + USERNAME + '. Ask out loud — I’ll answer and listen again.'
        : 'Ask out loud — I’ll answer and listen again.';
      appendChat('assistant', intro);
      speakText(intro).then(startListening);
    }

    // Bind UI
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
    });
    if (submitBtn) submitBtn.addEventListener('click', function () { onAskClick(); });
    if (clearBtn) clearBtn.addEventListener('click', function () {
      HISTORY = [];
      try { sessionStorage.removeItem('tv_ai_history'); } catch (e) {}
      renderFollowUps([]);
      var log = document.getElementById('aiChatLog');
      if (log) log.textContent = '';
      appendChat('assistant', 'Cleared. Ask a fresh question whenever you\'re ready.');
    });
    if (questionEl) questionEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') onAskClick();
    });
    if (tdBtn) tdBtn.addEventListener('click', runTradeDoctor);
    if (coachBtn) coachBtn.addEventListener('click', function () {
      var SR = global.SpeechRecognition || global.webkitSpeechRecognition;
      if (!SR) {
        appendChat('assistant', 'Coach Talk isn’t supported in this browser. Use typed chat or Play Voice Review.');
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

    var tabKey = 'tv_ai_tab';
    var savedTab = 'today';
    try { savedTab = sessionStorage.getItem(tabKey) || 'today'; } catch (e) {}
    if (!['today', 'review', 'setup'].includes(savedTab)) savedTab = 'today';
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
