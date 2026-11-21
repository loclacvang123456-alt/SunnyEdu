from django.test import SimpleTestCase

from apps.reporting.report_services import _recommend_exercises


def exercise(name, category, formats, pattern_formats=None):
    return {
        "assignment_id": name,
        "title": name,
        "course_name": category,
        "categories": {category} if category else set(),
        "formats": set(formats),
        "pattern_formats": pattern_formats or {},
        "is_ielts": category == "IELTS",
        "in_course": bool(category),
        "min_difficulty": 1,
    }


class RecommendationTests(SimpleTestCase):
    def setUp(self):
        self.topic = "Giao tiếp & Chào hỏi tình huống"
        self.catalog = {self.topic: [
            exercise("Chào hỏi", "PRIMARY", ["WORD_ORDER"], {self.topic: {"WORD_ORDER"}}),
            exercise("Chào hỏi trắc nghiệm", "PRIMARY", ["SINGLE_CHOICE"], {self.topic: {"SINGLE_CHOICE"}}),
            exercise("TESOL", "TESOL", ["WORD_ORDER"], {self.topic: {"WORD_ORDER"}}),
            exercise("THPT", "HIGH_SCHOOL", ["WORD_ORDER"], {self.topic: {"WORD_ORDER"}}),
            exercise("Không rõ trình độ", "", ["WORD_ORDER"], {self.topic: {"WORD_ORDER"}}),
            exercise("Khác dạng trong cùng đề", "PRIMARY", ["WORD_ORDER", "SINGLE_CHOICE"], {self.topic: {"SINGLE_CHOICE"}}),
        ]}

    def test_pattern_requires_level_and_same_question_type(self):
        result = _recommend_exercises(self.catalog, self.topic, preferred_categories={"PRIMARY"}, required_formats={"WORD_ORDER"}, match_pattern_format=True)
        self.assertEqual([item["title"] for item in result], ["Chào hỏi"])

    def test_unknown_or_incompatible_level_does_not_guess(self):
        self.assertEqual(_recommend_exercises(self.catalog, self.topic), [])
        self.assertEqual(_recommend_exercises(self.catalog, self.topic, preferred_categories={"IELTS"}), [])

    def test_prefer_uncompleted_and_exclude_source(self):
        result = _recommend_exercises(self.catalog, self.topic, preferred_categories={"PRIMARY"}, completed_assignment_ids={"Chào hỏi"}, exclude_assignment_id="Khác dạng trong cùng đề")
        self.assertEqual([item["title"] for item in result], ["Chào hỏi trắc nghiệm"])

    def test_does_not_present_completed_exercises_as_new_recommendations(self):
        completed = {item["assignment_id"] for item in self.catalog[self.topic]}
        self.assertEqual(_recommend_exercises(self.catalog, self.topic, preferred_categories={"PRIMARY"}, completed_assignment_ids=completed), [])

    def test_prioritizes_same_course_after_filtering_level(self):
        self.catalog[self.topic][1]["course_ids"] = {"course-1"}
        result = _recommend_exercises(self.catalog, self.topic, preferred_categories={"PRIMARY"}, preferred_course_ids={"course-1"})
        self.assertEqual(result[0]["title"], "Chào hỏi trắc nghiệm")
