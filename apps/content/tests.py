from pathlib import Path
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .services import parse_questions


class ImportTests(SimpleTestCase):
    def test_example_is_valid(self):
        data = (Path(__file__).resolve().parents[2] / 'docs/examples/questions.csv').read_bytes()
        rows = parse_questions(data, 'questions.csv')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]['correct_options'], 'A|C')

    def test_downloadable_example_matches_import_format(self):
        data = (Path(__file__).resolve().parents[2] / 'static/templates/mau-nhap-de.csv').read_bytes()
        rows = parse_questions(data, 'mau-nhap-de.csv')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]['correct_options'], 'A|C')

    def test_invalid_answer_rejected(self):
        data = (Path(__file__).resolve().parents[2] / 'docs/examples/questions.csv').read_bytes()
        data = data.replace(b'A|C', b'A|F')
        with self.assertRaises(ValidationError):
            parse_questions(data, 'questions.csv')

    def test_large_and_bad_header_rejected(self):
        with self.assertRaises(ValidationError):
            parse_questions(b'x' * (2*1024*1024+1), 'questions.csv')
        with self.assertRaises(ValidationError):
            parse_questions(b'prompt\nHi\n', 'questions.csv')


from django.contrib.auth import get_user_model
from django.test import TestCase
from .models import ExamVersion
from .services import preview_question_import, commit_question_import, publish_version


class ImportIntegrationTests(TestCase):
    def test_commit_is_idempotent_and_publish_validates(self):
        owner = get_user_model().objects.create_user(username='owner', role='OWNER', display_name='Owner', password='test-pass-123')
        data = (Path(__file__).resolve().parents[2] / 'docs/examples/questions.csv').read_bytes()
        batch = preview_question_import(owner, data, 'questions.csv')
        first = commit_question_import(owner, batch.id, batch.source_digest, 'Bài mẫu')
        second = commit_question_import(owner, batch.id, batch.source_digest, 'Bài mẫu')
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.questions.count(), 3)
        self.assertEqual(first.questions.get(position=2).answer_keys.count(), 2)
        published = publish_version(first.pk, 0)
        self.assertEqual(published.status, ExamVersion.Status.PUBLISHED)
        with self.assertRaises(ValidationError):
            publish_version(first.pk, 0)

    def test_full_question_types_csv_and_xlsx_import_and_publish(self):
        owner = get_user_model().objects.create_user(username='owner-full', role='OWNER', display_name='Owner', password='test-pass-123')
        root = Path(__file__).resolve().parents[2]
        expected_types = [
            'SINGLE_CHOICE',
            'SINGLE_CHOICE',
            'MULTIPLE_CHOICE',
            'STRESS_CHOICE',
            'WORD_ORDER',
            'SENTENCE_TRANSFORM',
            'TEXT',
            'AUDIO',
        ]
        for filename in ('de-mau-full-dang-bai.csv', 'de-mau-full-dang-bai.xlsx'):
            data = (root / filename).read_bytes()
            batch = preview_question_import(owner, data, filename)
            version = commit_question_import(owner, batch.id, batch.source_digest, f'Full {filename}')
            self.assertEqual(list(version.questions.values_list('type', flat=True)), expected_types)
            published = publish_version(version.pk, version.revision)
            self.assertEqual(published.status, ExamVersion.Status.PUBLISHED)

    def test_minimal_prompt_and_answer_only_csv_import_and_publish(self):
        from openpyxl import load_workbook

        owner = get_user_model().objects.create_user(username='owner-minimal', role='OWNER', display_name='Owner Minimal', password='test-pass-123')
        root = Path(__file__).resolve().parents[2]
        data = (root / 'bai-tap-du-dang-bai-mau.csv').read_bytes()
        batch = preview_question_import(owner, data, 'bai-tap-du-dang-bai-mau.csv')
        version = commit_question_import(owner, batch.id, batch.source_digest, 'Minimal Full Types')
        expected_types = [
            'SINGLE_CHOICE',
            'SINGLE_CHOICE',
            'SINGLE_CHOICE',
            'MULTIPLE_CHOICE',
            'STRESS_CHOICE',
            'WORD_ORDER',
            'SENTENCE_TRANSFORM',
            'TEXT',
            'AUDIO',
        ]
        self.assertEqual(list(version.questions.order_by('position').values_list('type', flat=True)), expected_types)
        published = publish_version(version.pk, version.revision)
        self.assertEqual(published.status, ExamVersion.Status.PUBLISHED)
        for q in published.questions.all():
            self.assertTrue(q.question_tags.filter(tag__kind='TOPIC', tag__skill=q.skill).exists())

        wb = load_workbook(root / 'de-mau-full-dang-bai.xlsx')
        dvs = wb['questions'].data_validations.dataValidation
        self.assertEqual(len(dvs), 3)


class QuestionGameModeTests(TestCase):
    def test_question_game_choice_is_validated_preserved_and_cloned(self):
        from .editor_services import clone_version, upsert_question
        from .models import Exam
        owner = get_user_model().objects.create_user(username='question-game-owner', role='OWNER')
        exam = Exam.objects.create(title='Game choice', created_by=owner)
        version = ExamVersion.objects.create(exam=exam, number=1)
        payload = {'type': 'SINGLE_CHOICE', 'skill': 'READING', 'difficulty': 'FOUNDATION', 'prompt': 'Choose', 'max_points': '1', 'topic_tags': ['Words'], 'options': [{'content': 'A'}, {'content': 'B'}], 'correct_options': ['A'], 'pirate_game': True}
        question, version = upsert_question(owner, version.id, 0, payload)
        self.assertIs(question.pirate_game, True)
        self.assertIs(clone_version(owner, version.id).questions.get().pirate_game, True)
        payload.pop('pirate_game')
        question, version = upsert_question(owner, version.id, version.revision, payload, question.id)
        self.assertIs(question.pirate_game, True)
        payload.update(type='MULTIPLE_CHOICE', correct_options=['A', 'B'], pirate_game=True)
        with self.assertRaises(ValidationError):
            upsert_question(owner, version.id, version.revision, payload, question.id)
