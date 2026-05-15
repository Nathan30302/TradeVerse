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
    'audio/mpeg',
    'audio/wav',
    'audio/x-wav',
    'audio/ogg',
    'video/webm',
    'application/octet-stream',
})


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

    filename = upload.filename if '.' in upload.filename else 'recording.webm'

    try:
        resp = requests.post(
            'https://api.openai.com/v1/audio/transcriptions',
            headers={'Authorization': f'Bearer {api_key}'},
            files={'file': (filename, raw, content_type)},
            data={'model': 'whisper-1'},
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
