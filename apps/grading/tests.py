from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .services import rubric_points


class RubricTests(SimpleTestCase):
    def test_points_are_decimal_and_half_up(self):
        self.assertEqual(rubric_points(Decimal('10.00'), [3, 2, 4, 3]), Decimal('7.50'))
        self.assertEqual(rubric_points(Decimal('0.10'), [1, 0, 0, 0]), Decimal('0.01'))

    def test_invalid_scores_rejected(self):
        for levels in ([1, 2, 3], [1, 2, 3, 5], [1, 2, 3, True]):
            with self.assertRaises(ValidationError):
                rubric_points(Decimal('10'), levels)
