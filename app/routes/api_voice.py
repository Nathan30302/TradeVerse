"""
Voice transcription API (OpenAI Whisper) for browsers without Web Speech API.

Used as a fallback in in-app browsers (Instagram, Facebook, etc.) where
SpeechRecognition is unavailable but microphone capture may still work.
"""

from __future__ import annotations

import os

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

_WHISPER_PROMPT = (
    "Trading journal. Symbols: EURUSD, XAUUSD, GBPUSD, USDJPY, US30, NAS100, BTCUSD. "
    "Words: buy, sell, long, short, entry, stop loss, take profit, lot size, pips, "
    "London, New York, Asia, liquidity, breakout."
)

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

    try:
        resp = requests.post(
            'https://api.openai.com/v1/audio/transcriptions',
            headers={'Authorization': f'Bearer {api_key}'},
            files={'file': (filename, raw, content_type)},
            data={
                'model': 'whisper-1',
                'language': 'en',
                'prompt': _WHISPER_PROMPT,
            },
            timeout=90,
        )
    except requests.RequestException as exc:
        current_app.logger.warning('Whisper request failed: %s', exc)
        return jsonify({'error': 'Could not reach transcription service. Try again.'}), 502

    if resp.status_code != 200:
        current_app.logger.warning('Whisper HTTP %s: %s', resp.status_code, resp.text[:300])
        return jsonify({'error': 'Transcription failed. Try again or type your note.'}), 502

    try:
        data = resp.json()
    except ValueError:
        return jsonify({'error': 'Invalid transcription response.'}), 502

    text = (data.get('text') if isinstance(data, dict) else '') or ''
    text = str(text).strip()
    if not text:
        return jsonify({'error': 'No speech detected in recording.'}), 422

    return jsonify({'text': text})


_NEURAL_VOICES = frozenset({
    'alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer', 'verse',
})


@bp.route('/speak', methods=['POST'])
@login_required
def speak():
    """Neural TTS via OpenAI — short spoken coach replies (mp3)."""
    from flask_login import current_user
    from app.services.entitlements import user_has_feature
    from app.services.ai_buddy_voice import truncate_for_speech

    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not api_key:
        return jsonify({'error': 'Speech is not configured.', 'fallback': True}), 503
    if not user_has_feature(current_user, 'ai_web'):
        return jsonify({'error': 'Neural voice requires Pro Plus.', 'fallback': True}), 403

    payload = request.get_json(silent=True) or {}
    text = truncate_for_speech(str(payload.get('text') or ''))
    if not text:
        return jsonify({'error': 'Nothing to speak.'}), 400
    voice = str(payload.get('voice') or 'coral').strip().lower()
    if voice not in _NEURAL_VOICES:
        voice = 'coral'

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
        body = {
            'model': model,
            'voice': voice,
            'input': text,
            'response_format': 'mp3',
        }
        if model.startswith('gpt-4o'):
            body['instructions'] = (
                'Speak like a calm senior trading mentor: warm, steady, concise, never hype.'
            )
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
        'voices': sorted(_NEURAL_VOICES) if enabled else [],
        'default': 'coral',
    })
