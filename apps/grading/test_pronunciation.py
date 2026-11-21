import base64
import io
import json
import wave
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from .pronunciation import (InvalidPractice, PronunciationBusy, PronunciationUnavailable, assess,
                            azure_slot, configured, parse_result, validate_reference, validate_wav)


def sample_wav(rate=16000, channels=1, width=2, frames=1600):
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(channels); audio.setsampwidth(width); audio.setframerate(rate)
        audio.writeframes(b'\x00' * (frames * channels * width))
    return output.getvalue()


class PronunciationServiceTests(SimpleTestCase):
    def test_input_validation(self):
        self.assertEqual(validate_reference(' Hello world! '), 'Hello world!')
        for bad in ['', 'hello@outside', 'x' * 201, '123', None]:
            with self.assertRaises(InvalidPractice): validate_reference(bad)
        validate_wav(sample_wav())
        for bad in [b'not wav', sample_wav(rate=44100), sample_wav(channels=2), sample_wav(width=1), sample_wav(frames=240001)]:
            with self.assertRaises(InvalidPractice): validate_wav(bad)
        for region in ['westus.evil.com', 'WESTUS', '../eastus', 'eastus:123']:
            self.assertFalse(configured('key', region))

    def test_result_not_fabricated(self):
        self.assertEqual(parse_result({'RecognitionStatus':'NoMatch'}), {'recognition':False,'words':[]})
        with self.assertRaises(PronunciationUnavailable): parse_result({'RecognitionStatus':'Success','NBest':[{}]})
        data = {'RecognitionStatus':'Success', 'NBest':[{'Words':[{'Word':'cat', 'PronunciationAssessment':{'AccuracyScore':60,'ErrorType':'Mispronunciation'}, 'Phonemes':[{'Phoneme':'æ','PronunciationAssessment':{'AccuracyScore':48}}]}]}]}
        result = parse_result(data)
        self.assertEqual(result['words'][0]['phonemes'][0], {'ipa':'æ','score':48})
        self.assertEqual(result['words'][0]['error_type'], 'Mispronunciation')

    @patch('apps.grading.pronunciation.azure_slot', return_value=nullcontext())
    @patch('apps.grading.pronunciation.build_opener')
    def test_azure_headers_and_payload(self, opener, slot):
        body = {'RecognitionStatus':'Success','NBest':[{'Words':[{'Word':'hello','AccuracyScore':85,'Phonemes':[{'Phoneme':'h','AccuracyScore':90}]}]}]}
        response = MagicMock(); response.read.return_value = json.dumps(body).encode()
        opener.return_value.open.return_value.__enter__.return_value = response
        result = assess('hello', sample_wav(), 'secret-key', 'eastus')
        self.assertEqual(result['words'][0]['phonemes'][0]['ipa'], 'h')
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://eastus.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=en-US&format=detailed')
        headers = {k.lower(): v for k, v in request.header_items()}
        params = json.loads(base64.b64decode(headers['pronunciation-assessment']))
        self.assertEqual(params['PhonemeAlphabet'], 'IPA')
        self.assertEqual(params['ReferenceText'], 'hello')
        self.assertEqual(headers['ocp-apim-subscription-key'], 'secret-key')
        self.assertEqual(request.data, sample_wav())
        self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 10)


@override_settings(ROOT_URLCONF='apps.grading.pronunciation_urls')
class PronunciationViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='speak-student', role='STUDENT', display_name='Em')
        self.owner = User.objects.create_user(username='speak-owner', role='OWNER', display_name='Giáo viên')
        self.client = Client(enforce_csrf_checks=True)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session; now = timezone.now().isoformat()
        session['auth_epoch'] = user.auth_epoch; session['issued_at'] = now; session['last_activity'] = now
        session['remember_device'] = False; session.save()
        self.client.get('/speaking/practice/')
        return self.client.cookies['csrftoken'].value

    def post(self, csrf=None, consent='yes', audio=None):
        return self.client.post('/api/v1/speaking/practice/check/', {'reference':'Hello world', 'consent':consent,
            'audio':SimpleUploadedFile('sample.wav', sample_wav() if audio is None else audio, content_type='audio/wav')},
            **({'HTTP_X_CSRFTOKEN':csrf} if csrf else {}))

    @patch.dict('os.environ', {'AZURE_SPEECH_KEY':'key','AZURE_SPEECH_REGION':'eastus'})
    @patch('apps.grading.pronunciation_views.assess')
    def test_student_consent_csrf_and_result(self, service):
        csrf = self.login(self.student)
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.post(csrf, consent='no').status_code, 422)
        self.assertEqual(self.post(csrf, audio=b'no').status_code, 422)
        service.assert_not_called()
        service.return_value = {'recognition':True,'words':[{'word':'Hello','score':88,'error_type':'None','phonemes':[]}]}
        response = self.post(csrf)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['threshold'], 75)
        self.assertNotIn('key', response.content.decode())
        service.assert_called_once()

    @patch.dict('os.environ', {'AZURE_SPEECH_KEY':'','AZURE_SPEECH_REGION':''})
    @patch('apps.grading.pronunciation_views.assess')
    def test_missing_config_does_not_call_provider(self, service):
        csrf = self.login(self.student)
        page = self.client.get('/speaking/practice/')
        self.assertContains(page, 'chưa được giáo viên cấu hình')
        self.assertEqual(self.post(csrf).status_code, 503)
        service.assert_not_called()

    @patch.dict('os.environ', {'AZURE_SPEECH_KEY':'key','AZURE_SPEECH_REGION':'eastus'})
    @patch('apps.grading.pronunciation_views.assess')
    def test_owner_cannot_use_student_endpoint(self, service):
        csrf = self.login(self.owner)
        self.assertEqual(self.post(csrf).status_code, 401)
        service.assert_not_called()


class PronunciationSlotTests(TransactionTestCase):
    def test_one_global_slot_and_release(self):
        with azure_slot():
            with self.assertRaises(PronunciationBusy):
                with azure_slot():
                    pass
        with azure_slot():
            pass
