"""
Test auto title detection and batch import logic.
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.content.views import _clean_default_title
from apps.content.services import parse_questions, preview_question_import, commit_question_import
from apps.accounts.models import User
from apps.content.models import Exam

def run_tests():
    print("=== Testing Auto Title Detection ===")
    assert _clean_default_title("IOE 5 - TEST 1110T - Phan 1.csv") == "IOE 5 - TEST 1110T - Phan 1"
    assert _clean_default_title("de_thi_giua_ki_2_lop_3.xlsx") == "de thi giua ki 2 lop 3"
    assert _clean_default_title("simple.csv") == "simple"
    assert _clean_default_title(".csv") == "Đề thi mới"
    print("✓ _clean_default_title passed all test cases!")

    print("\n=== Testing Question Parsing on Converted CSVs ===")
    sample_csv = os.path.join(str(BASE_DIR), "quizzes_csv", "IOE 5 - TEST 1110T - Phan 1.csv")
    if not os.path.exists(sample_csv):
        # Pick any CSV in quizzes_csv
        files = [f for f in os.listdir(os.path.join(str(BASE_DIR), "quizzes_csv")) if f.endswith(".csv") and not f.startswith("danh-")]
        sample_csv = os.path.join(str(BASE_DIR), "quizzes_csv", files[0])
    
    with open(sample_csv, "rb") as f:
        data = f.read()

    rows = parse_questions(data, os.path.basename(sample_csv))
    assert len(rows) > 0, "Expected parsed rows"
    print(f"✓ Parsed {len(rows)} questions from {os.path.basename(sample_csv)} successfully!")

    print("\n=== All Import Logic Tests Passed Successfully! ===")

if __name__ == '__main__':
    run_tests()
