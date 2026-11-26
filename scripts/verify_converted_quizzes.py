"""
Standalone verification test for converted CSV quizzes and EDUWEB parser compatibility.
"""
import os
import sys
import csv
import random
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from apps.content.services import parse_questions, FIELDS

OUTPUT_DIR = os.path.join(str(BASE_DIR), "quizzes_csv")
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "danh-muc-de-thi.csv")
REVIEW_PATH = os.path.join(OUTPUT_DIR, "danh-sach-cau-can-ra-soat-dap-an.csv")

def run_checks():
    print("=== Running Verification Checks ===")

    # 1. Check directories and summary files
    assert os.path.isdir(OUTPUT_DIR), f"Directory missing: {OUTPUT_DIR}"
    assert os.path.isfile(MANIFEST_PATH), f"Manifest file missing: {MANIFEST_PATH}"
    assert os.path.isfile(REVIEW_PATH), f"Review file missing: {REVIEW_PATH}"

    # 2. Check manifest content
    with open(MANIFEST_PATH, 'r', encoding='utf-8-sig') as f:
        reader = list(csv.DictReader(f))
        assert len(reader) >= 1000, f"Expected >= 1000 exams, got {len(reader)}"
        print(f"✓ Manifest verified: {len(reader)} exams registered.")

    # 3. Check review file
    with open(REVIEW_PATH, 'r', encoding='utf-8-sig') as f:
        review_rows = list(csv.DictReader(f))
        assert len(review_rows) > 0, "Expected review entries"
        print(f"✓ Review list verified: {len(review_rows)} flagged questions for review.")

    # 4. Check all CSV filenames & sample 30 random files for deep validation
    all_files = [fn for fn in os.listdir(OUTPUT_DIR) if fn.endswith('.csv') and not fn.startswith('danh-')]
    assert len(all_files) == len(reader), f"File count mismatch: {len(all_files)} vs {len(reader)}"
    print(f"✓ File count matches manifest: {len(all_files)} CSV files on disk.")

    random.seed(42)
    sample_files = random.sample(all_files, 30)
    for fn in sample_files:
        fp = os.path.join(OUTPUT_DIR, fn)
        with open(fp, 'rb') as f:
            data = f.read()
        
        # Test EDUWEB validator
        rows = parse_questions(data, fn)
        assert 1 <= len(rows) <= 50, f"Exceeded 50 questions in {fn}: {len(rows)}"
        for idx, r in enumerate(rows, start=1):
            assert int(r['position']) == idx, f"Wrong position in {fn}: {r['position']} != {idx}"
            assert r['type'] in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'WORD_ORDER', 'SENTENCE_TRANSFORM', 'TEXT', 'AUDIO'), f"Unknown type: {r['type']}"
            assert Decimal_ok(r['max_points']), f"Invalid points: {r['max_points']}"

    print(f"✓ 30 randomly sampled exam CSVs parsed and validated 100% successfully!")
    print("=== All verification checks PASSED! ===")

def Decimal_ok(val):
    try:
        from decimal import Decimal
        d = Decimal(val)
        return Decimal('0.01') <= d <= Decimal('100.00')
    except Exception:
        return False

if __name__ == '__main__':
    run_checks()
