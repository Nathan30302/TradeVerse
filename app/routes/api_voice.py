"""
Voice transcription API (OpenAI Whisper) for browsers without Web Speech API.

Used as a fallback in in-app browsers (Instagram, Facebook, etc.) where
SpeechRecognition is unavailable but microphone capture may still work.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

import requests
from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

bp = Blueprint('api_voice', __name__, url_prefix='/api/voice')

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_TYPES = frozenset({
    'audio/webm',
    'audio/mp4',
    'audio/m4a',
    'audio/x-m4a',
    'audio/aac',
    'audio/mpeg',
    'audio/wav',
    'audio/x-wav',
    'audio/ogg',
    'audio/3gpp',
    'video/webm',
    'video/mp4',
    'application/octet-stream',
})

_EXT_FOR_TYPE = {
    'audio/mp4': 'm4a',
    'audio/m4a': 'm4a',
    'audio/x-m4a': 'm4a',
    'audio/aac': 'm4a',
    'audio/mpeg': 'mp3',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/ogg': 'ogg',
    'audio/3gpp': '3gp',
    'video/mp4': 'mp4',
    'video/webm': 'webm',
    'audio/webm': 'webm',
}


def _transcribe_enabled() -> bool:
    return bool(os.environ.get('OPENAI_API_KEY', '').strip())


def voice_output_ready() -> bool:
    """True when this machine can speak for every device, including a phone."""
    if _transcribe_enabled():
        return True
    return sys.platform == 'darwin' and bool(shutil.which('say'))


# Mac voices. The phone plays this audio, so it does not use its own robot voice.
_SAY_CAST = {
    'marin': ('Sandy', '168'),
    'cedar': ('Reed', '160'),
    'sage': ('Tessa', '156'),
}


def _speak_on_mac(text: str, voice_id: str) -> bytes | None:
    """Render speech with the Mac's natural voices and return a wav."""
    if sys.platform != 'darwin' or not shutil.which('say'):
        return None
    name, rate = _SAY_CAST.get(voice_id, ('Sandy', '168'))
    spoken = (text or '').replace('—', ', ').replace('–', ', ').strip()
    if not spoken:
        return None
    fd, path = tempfile.mkstemp(suffix='.wav')
    os.close(fd)
    try:
        cmd = ['say', '-v', name, '-r', rate, '-o', path, '--data-format=LEI16@22050', spoken]
        proc = subprocess.run(cmd, capture_output=True, timeout=25)
        if proc.returncode != 0:
            proc = subprocess.run(
                ['say', '-r', rate, '-o', path, '--data-format=LEI16@22050', spoken],
                capture_output=True,
                timeout=25,
            )
        if proc.returncode != 0:
            return None
        with open(path, 'rb') as handle:
            data = handle.read()
        return data if len(data) > 1000 else None
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@bp.route('/status', methods=['GET'])
@login_required
def status():
    """Report whether server-side transcription is available."""
    return jsonify({
        'enabled': _transcribe_enabled(),
        'max_bytes': _MAX_BYTES,
    })


@bp.route('/transcribe', methods=['POST'])
@login_required
def transcribe():
    """Transcribe uploaded audio via OpenAI Whisper."""
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not api_key:
        return jsonify({'error': 'Voice transcription is not configured on this server.'}), 503

    upload = request.files.get('audio')
    if not upload or not upload.filename:
        return jsonify({'error': 'No audio file received.'}), 400

    raw = upload.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        return jsonify({'error': 'Recording too long — try a shorter clip.'}), 413
    if not raw:
        return jsonify({'error': 'Empty audio file.'}), 400

    content_type = (upload.content_type or 'audio/webm').split(';')[0].strip().lower()
    if content_type not in _ALLOWED_TYPES:
        content_type = 'audio/webm'

    incoming = upload.filename or ''
    ext = incoming.rsplit('.', 1)[-1].lower() if '.' in incoming else ''
    if ext not in ('webm', 'm4a', 'mp3', 'wav', 'ogg', 'mp4', '3gp', 'aac'):
        ext = _EXT_FOR_TYPE.get(content_type, 'webm')
    filename = f'recording.{ext}'

    models = [
        os.environ.get('OPENAI_TRANSCRIBE_MODEL', '').strip(),
        'gpt-4o-transcribe',
        'gpt-4o-mini-transcribe',
        'whisper-1',
    ]
    seen = set()
    models = [m for m in models if m and not (m in seen or seen.add(m))]

    last_err = ''
    data = None
    for model in models:
        form = {
            'model': model,
            'language': 'en',
        }
        if model == 'whisper-1':
            form['temperature'] = '0'
        elif model.startswith('gpt-4o'):
            # Verbatim only. A symbol glossary made the model substitute other trading words.
            hint = str(request.form.get('hint') or '').strip().replace('\n', ' ')[:240]
            prompt = (
                'Transcribe verbatim. Keep the speaker\'s exact words, slang, and numbers. '
                'Do not paraphrase, summarize, or replace a word with a different one.'
            )
            if hint and 'trading journal' not in hint.lower():
                prompt += ' A rough live caption, which is often wrong: ' + hint
            form['prompt'] = prompt
        try:
            resp = requests.post(
                'https://api.openai.com/v1/audio/transcriptions',
                headers={'Authorization': f'Bearer {api_key}'},
                files={'file': (filename, raw, content_type)},
                data=form,
                timeout=25,
            )
        except requests.RequestException as exc:
            current_app.logger.warning('Whisper request failed (%s): %s', model, exc)
            last_err = str(exc)
            continue
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                last_err = 'invalid json'
                continue
            break
        last_err = resp.text[:300]
        current_app.logger.info('Transcribe model %s HTTP %s — trying next', model, resp.status_code)

    if data is None:
        current_app.logger.warning('Transcription failed: %s', last_err)
        return jsonify({'error': 'Transcription failed. Try again or type your note.'}), 502

    try:
        text = (data.get('text') if isinstance(data, dict) else '') or ''
    except Exception:
        text = ''
    text = str(text).strip()
    # Drop leaked glossary / instruction lines if a model still prepends them.
    low = text.lower()
    if low.startswith('trading journal') or 'symbols: eurusd' in low:
        text = ''
    if not text:
        return jsonify({'error': 'No speech detected in recording.'}), 422

    return jsonify({'text': text})


# Acting notes for gpt-4o-mini-tts. Concrete pace and tone, one breath.
_HUMAN = (
    "Voice: a friend across the desk after the close. "
    "Tone: warm, easy, contractions, a natural rise and fall. "
    "Pace: conversational, unhurried, never clipped. "
    "Delivery: one continuous thought. A short breath only before a question. "
    "Clarity: everyday speech, not an announcer and not a recording."
)
_CLASSIC_VOICES = frozenset({
    'alloy', 'ash', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer',
})
_VOICE_CAST = {
    'marin': {
        'label': 'Maya',
        'hint': 'Close, real',
        'speed': 0.96,
        'classic': 'shimmer',
        'instructions': _HUMAN + " A woman in her thirties. Close to the mic, soft smile in the voice, unhurried.",
    },
    'cedar': {
        'label': 'Noah',
        'hint': 'Warm, grounded',
        'speed': 0.94,
        'classic': 'onyx',
        'instructions': _HUMAN + " A man in his thirties. Low, easy, leaning back, like he's glad you sat down.",
    },
    'sage': {
        'label': 'Sage',
        'hint': 'Quiet, sure',
        'speed': 0.95,
        'classic': 'sage',
        'instructions': _HUMAN + " A woman with a quiet, steady voice, a little lower, thinking it through with you.",
    },
}
_NEURAL_VOICES = frozenset(_VOICE_CAST)


@bp.route('/speak', methods=['POST'])
@login_required
def speak():
    """Neural TTS via OpenAI — short spoken coach replies (mp3)."""
    from flask_login import current_user
    from app.services.entitlements import user_has_feature
    from app.services.ai_buddy_voice import truncate_for_speech

    payload = request.get_json(silent=True) or {}
    text = truncate_for_speech(str(payload.get('text') or ''))
    if not text:
        return jsonify({'error': 'Nothing to speak.'}), 400
    voice = str(payload.get('voice') or 'marin').strip().lower()
    if voice in ('coral', 'ash'):
        voice = {'coral': 'marin', 'ash': 'cedar'}[voice]
    if voice not in _VOICE_CAST:
        voice = 'marin'

    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not (api_key and user_has_feature(current_user, 'ai_web')):
        local = _speak_on_mac(text, voice)
        if local:
            from flask import Response
            return Response(
                local,
                mimetype='audio/wav',
                headers={'Cache-Control': 'no-store', 'X-TTS-Model': 'mac-say'},
            )
        if api_key:
            return jsonify({'error': 'Neural voice requires Pro Plus.', 'fallback': True}), 403
        return jsonify({'error': 'Speech is not configured.', 'fallback': True}), 503

    # Prefer higher-quality models; fall back so older accounts keep working.
    models = [
        os.environ.get('OPENAI_TTS_MODEL', '').strip(),
        'gpt-4o-mini-tts',
        'tts-1-hd',
        'tts-1',
    ]
    models = [m for m in models if m]
    # Deduplicate while preserving order
    seen = set()
    models = [m for m in models if not (m in seen or seen.add(m))]

    last_err = ''
    for model in models:
        spoken_voice = voice
        if not model.startswith('gpt-4o') and spoken_voice not in _CLASSIC_VOICES:
            spoken_voice = _VOICE_CAST[voice].get('classic') or 'sage'
        body = {
            'model': model,
            'voice': spoken_voice,
            'input': text,
            'response_format': 'mp3',
            'speed': _VOICE_CAST[voice].get('speed') or 0.94,
        }
        if model.startswith('gpt-4o'):
            body['instructions'] = _VOICE_CAST[voice]['instructions']
        try:
            resp = requests.post(
                'https://api.openai.com/v1/audio/speech',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json=body,
                timeout=60,
            )
        except requests.RequestException as exc:
            current_app.logger.warning('TTS request failed (%s): %s', model, exc)
            last_err = str(exc)
            continue

        if resp.status_code == 200:
            from flask import Response

            return Response(
                resp.content,
                mimetype='audio/mpeg',
                headers={
                    'Cache-Control': 'no-store',
                    'X-TTS-Model': model,
                },
            )
        last_err = resp.text[:300]
        current_app.logger.info('TTS model %s HTTP %s — trying next', model, resp.status_code)

    current_app.logger.warning('TTS failed all models: %s', last_err)
    local = _speak_on_mac(text, voice)
    if local:
        from flask import Response
        return Response(
            local,
            mimetype='audio/wav',
            headers={'Cache-Control': 'no-store', 'X-TTS-Model': 'mac-say'},
        )
    return jsonify({'error': 'Speech synthesis failed.', 'fallback': True}), 502


@bp.route('/voices', methods=['GET'])
@login_required
def voices():
    """List neural TTS voice ids when available."""
    from flask_login import current_user
    from app.services.entitlements import user_has_feature

    enabled = _transcribe_enabled() and user_has_feature(current_user, 'ai_web')
    return jsonify({
        'enabled': enabled,
        'voices': [
            {'id': key, 'label': meta['label'], 'hint': meta['hint']}
            for key, meta in _VOICE_CAST.items()
        ],
        'default': 'marin',
    })
