"""Optional private LanguageTool integration for practice writing.

This module never contacts LanguageTool's public service. The caller must pass
an explicitly configured loopback URL and handle errors without logging text.
"""
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_TEXT_CHARS = 10000
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_MATCHES = 100


class AssistanceUnavailable(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_endpoint(configured_url):
    """Return a fixed-loopback endpoint or fail closed for unsafe URLs."""
    if not isinstance(configured_url, str) or not configured_url:
        raise AssistanceUnavailable
    try:
        parsed = urlsplit(configured_url)
        port = parsed.port
        if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1')
                or parsed.username is not None or parsed.password is not None
                or parsed.path != '/v2/check' or parsed.query or parsed.fragment
                or port is None or not 1 <= port <= 65535):
            raise AssistanceUnavailable
    except ValueError:
        raise AssistanceUnavailable from None
    # Canonicalizing localhost prevents hosts-file DNS changes and proxy use.
    return urlunsplit(('http', f'127.0.0.1:{port}', '/v2/check', '', ''))


def check_writing(text, configured_url, timeout=10):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
        raise ValueError('Invalid text')
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('Invalid text') from None
    endpoint = local_endpoint(configured_url)
    data = urlencode({'language': 'en-US', 'text': text}).encode('utf-8')
    request = Request(endpoint, data=data, method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8', 'Accept': 'application/json'})
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise AssistanceUnavailable
        payload = json.loads(body.decode('utf-8'))
        matches = payload.get('matches')
        if not isinstance(matches, list):
            raise AssistanceUnavailable
    except (OSError, URLError, HTTPError, socket.timeout, UnicodeError, json.JSONDecodeError, AttributeError):
        raise AssistanceUnavailable from None
    max_offset = len(text.encode('utf-16-le')) // 2
    safe = []
    for match in matches[:MAX_MATCHES]:
        if not isinstance(match, dict):
            continue
        offset, length, message = match.get('offset'), match.get('length'), match.get('message')
        if (type(offset) is not int or type(length) is not int or offset < 0 or length < 1
                or offset + length > max_offset or not isinstance(message, str)):
            continue
        replacements = match.get('replacements', [])
        if not isinstance(replacements, list):
            replacements = []
        suggestions = [item['value'][:200] for item in replacements[:5]
                       if isinstance(item, dict) and isinstance(item.get('value'), str)]
        rule = match.get('rule')
        category = rule.get('category') if isinstance(rule, dict) else None
        label = category.get('name', '') if isinstance(category, dict) else ''
        safe.append({'offset': offset, 'length': length, 'message': message[:500],
                     'suggestions': suggestions, 'category': label[:100] if isinstance(label, str) else ''})
    return {'offset_encoding': 'utf-16', 'matches': safe}
