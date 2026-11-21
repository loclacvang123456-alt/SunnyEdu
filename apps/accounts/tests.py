from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .services import normalize_code, digest_code


class CodeTests(SimpleTestCase):
    def test_normalization_and_hmac(self):
        value = '01234-56789-ABCDE-FGHJK'
        self.assertEqual(normalize_code(value.lower()), '0123456789ABCDEFGHJK')
        self.assertEqual(digest_code(normalize_code(value), 'key'), digest_code(normalize_code(value.lower()), 'key'))
        self.assertNotEqual(digest_code(normalize_code(value), 'key'), digest_code(normalize_code(value), 'other'))

    def test_invalid_code(self):
        for value in ['short', '0123456789ABCDEFGHIJ', '0' * 21]:
            with self.assertRaises(ValidationError):
                normalize_code(value)
