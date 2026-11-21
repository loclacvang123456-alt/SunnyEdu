from django.test import SimpleTestCase

from .auto_tagging import infer_question_error_names


class ErrorTagSuggestionTests(SimpleTestCase):
    def test_specific_question_type_takes_priority_over_stray_grammar_words(self):
        infer = infer_question_error_names
        self.assertEqual(infer('SINGLE_CHOICE', 'READING', "Choose the word closest in meaning to 'important':"), ['Từ vựng: từ đồng nghĩa'])
        self.assertEqual(infer('SINGLE_CHOICE', 'READING', 'How does Lan go to school every morning?', has_passage=True), ['Đọc hiểu: thông tin trong bài'])
        self.assertEqual(infer('WORD_ORDER', 'WRITING', 'Sắp xếp câu', options_text='they went to school'), ['Sắp xếp câu: trật tự từ'])
        self.assertEqual(infer('STRESS_CHOICE', 'READING', 'Choose the stressed syllable', options_text='visited'), ['Phát âm: trọng âm của từ'])
        self.assertEqual(infer('TEXT', 'WRITING', 'Write about your day', options_text='went'), ['Viết: diễn đạt nội dung'])

    def test_unknown_and_teacher_selected_labels(self):
        infer = infer_question_error_names
        self.assertEqual(infer('SINGLE_CHOICE', 'READING', 'If it rains, we ___ at home.'), [])
        self.assertEqual(infer('SINGLE_CHOICE', 'READING', 'Any prompt', manual_errors=['Nhãn giáo viên']), ['Nhãn giáo viên'])
