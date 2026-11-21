"""Azure Speech pronunciation practice; transient data, never saved or logged.

Microsoft REST short-audio contract:
https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-speech-to-text-short
"""
import base64
import io
import json
import math
import re
import wave
from contextlib import contextmanager
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import psycopg
from django.db import connections

MAX_AUDIO_BYTES = 512 * 1024
MAX_SECONDS = 15
AZURE_LOCK_ID = 725419803192001
REFERENCE = re.compile(r"^[A-Za-z][A-Za-z\s.,!?'-]{0,199}$")
REGION = re.compile(r'^[a-z0-9]{2,32}$')


class PronunciationUnavailable(Exception):
    pass


class PronunciationBusy(Exception):
    pass


class InvalidPractice(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def configured(key, region):
    return isinstance(key, str) and bool(key.strip()) and isinstance(region, str) and bool(REGION.fullmatch(region))


def validate_reference(reference):
    if not isinstance(reference, str) or len(reference) > 200:
        raise InvalidPractice
    reference = reference.strip()
    if not REFERENCE.fullmatch(reference):
        raise InvalidPractice
    return reference


def validate_wav(blob):
    if not isinstance(blob, bytes) or len(blob) > MAX_AUDIO_BYTES or len(blob) < 44:
        raise InvalidPractice
    try:
        with wave.open(io.BytesIO(blob), 'rb') as wav:
            frames = wav.getnframes()
            if (wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000
                    or wav.getcomptype() != 'NONE' or not 0 < frames <= 16000 * MAX_SECONDS):
                raise InvalidPractice
            if len(wav.readframes(frames)) != frames * 2:
                raise InvalidPractice
    except (wave.Error, EOFError, ValueError, OSError):
        raise InvalidPractice from None


@contextmanager
def azure_slot():
    """A dedicated connection holds one PostgreSQL advisory lock cluster-wide."""
    db = connections['default']
    if db.vendor != 'postgresql':
        raise PronunciationUnavailable
    try:
        params = db.get_connection_params().copy()
        params['connect_timeout'] = 3
        with psycopg.connect(**params, autocommit=True) as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT pg_try_advisory_lock(%s)', (AZURE_LOCK_ID,))
                if not cursor.fetchone()[0]:
                    raise PronunciationBusy
            try:
                yield
            finally:
                # Closing the dedicated connection also releases the lock if this fails.
                with conn.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_unlock(%s)', (AZURE_LOCK_ID,))
    except (PronunciationBusy, PronunciationUnavailable):
        raise
    except psycopg.Error:
        raise PronunciationUnavailable from None


def _score(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return round(value, 1)


def _assessment_score(item):
    assessment = item.get('PronunciationAssessment')
    nested = assessment.get('AccuracyScore') if isinstance(assessment, dict) else None
    return _score(nested if nested is not None else item.get('AccuracyScore'))


def parse_result(payload):
    if not isinstance(payload, dict):
        raise PronunciationUnavailable
    if payload.get('RecognitionStatus') != 'Success':
        return {'recognition': False, 'words': []}
    best = payload.get('NBest')
    if not isinstance(best, list) or not best or not isinstance(best[0], dict):
        raise PronunciationUnavailable
    raw_words = best[0].get('Words')
    if not isinstance(raw_words, list):
        raise PronunciationUnavailable
    words = []
    for word in raw_words[:50]:
        if not isinstance(word, dict) or not isinstance(word.get('Word'), str):
            continue
        assessment = word.get('PronunciationAssessment')
        error_type = assessment.get('ErrorType', '') if isinstance(assessment, dict) else word.get('ErrorType', '')
        if error_type not in ('None', 'Omission', 'Insertion', 'Mispronunciation'):
            error_type = ''
        phonemes = []
        raw_phonemes = word.get('Phonemes', [])
        if isinstance(raw_phonemes, list):
            for phone in raw_phonemes[:40]:
                if isinstance(phone, dict) and isinstance(phone.get('Phoneme'), str):
                    phonemes.append({'ipa': phone['Phoneme'][:20], 'score': _assessment_score(phone)})
        words.append({'word': word['Word'][:200], 'score': _assessment_score(word), 'error_type': error_type, 'phonemes': phonemes})
    if not words:
        raise PronunciationUnavailable
    return {'recognition': True, 'words': words}


def assess(reference, blob, key, region):
    reference = validate_reference(reference)
    validate_wav(blob)
    if not configured(key, region):
        raise PronunciationUnavailable
    parameters = {'ReferenceText': reference, 'GradingSystem': 'HundredMark', 'Granularity': 'Phoneme',
                  'Dimension': 'Comprehensive', 'EnableMiscue': True, 'PhonemeAlphabet': 'IPA'}
    encoded = base64.b64encode(json.dumps(parameters, ensure_ascii=True).encode()).decode('ascii')
    endpoint = f'https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=en-US&format=detailed'
    request = Request(endpoint, data=blob, method='POST', headers={
        'Ocp-Apim-Subscription-Key': key, 'Pronunciation-Assessment': encoded,
        'Content-Type': 'audio/wav; codecs=audio/pcm; samplerate=16000', 'Accept': 'application/json'})
    try:
        with azure_slot():
            opener = build_opener(ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=10) as response:
                raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise PronunciationUnavailable
        return parse_result(json.loads(raw.decode('utf-8')))
    except (PronunciationBusy, PronunciationUnavailable):
        raise
    except (URLError, OSError, UnicodeError, ValueError):
        raise PronunciationUnavailable from None
