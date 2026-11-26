import difflib
import re
from decimal import Decimal


def _levenshtein(s1, s2):
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _is_minor_typo(w1, w2):
    s1, s2 = w1.lower(), w2.lower()
    dist = _levenshtein(s1, s2)
    if len(s2) <= 3:
        return dist == 1
    return dist <= 2


def tokenize_sentence(text):
    if not text:
        return []
    return re.findall(r"\w+|[^\w\s]", text.strip())


def grade_sentence_transform(student_text, standard_text, max_points):
    max_pts = Decimal(str(max_points))
    student_original = student_text or ""
    standard_original = standard_text or ""
    s_raw = student_original.strip()
    t_raw = standard_original.strip()

    s_tokens = tokenize_sentence(s_raw)
    t_tokens = tokenize_sentence(t_raw)

    if not s_raw:
        diff_tokens = [
            {
                "type": "missing",
                "student_word": "",
                "teacher_word": t,
                "is_error": True,
                "error_type": "major",
                "hint": f"Thiếu: '{t}'",
            }
            for t in t_tokens
        ]
        return {
            "points": Decimal("0.00"),
            "max_points": float(max_pts),
            "status": "wrong",
            "student_answer": s_raw,
            "standard_answer": t_raw,
            "diff_tokens": diff_tokens,
            "minor_errors": 0,
            "major_errors": len(t_tokens),
            "feedback": "Chưa nhập câu trả lời (0 điểm).",
        }

    matcher = difflib.SequenceMatcher(None, [t.lower() for t in s_tokens], [t.lower() for t in t_tokens])
    diff_tokens = []
    minor_error_count = 0
    major_error_count = 0
    error_details = []
    capitalization_hints = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for s_tok, t_tok in zip(s_tokens[i1:i2], t_tokens[j1:j2]):
                if s_tok != t_tok:
                    capitalization_hints.append(f"'{s_tok}' → '{t_tok}'")
                    diff_tokens.append({
                        "type": "equal",
                        "student_word": s_tok,
                        "teacher_word": t_tok,
                        "is_error": False,
                        "hint": "",
                    })
                else:
                    diff_tokens.append({
                        "type": "equal",
                        "student_word": s_tok,
                        "teacher_word": t_tok,
                        "is_error": False,
                        "hint": "",
                    })
        elif tag == "replace":
            s_slice = s_tokens[i1:i2]
            t_slice = t_tokens[j1:j2]
            if len(s_slice) == len(t_slice) == 1 and _is_minor_typo(s_slice[0], t_slice[0]):
                minor_error_count += 1
                err_hint = f"Lỗi chính tả '{s_slice[0]}' → '{t_slice[0]}'"
                error_details.append(err_hint)
                diff_tokens.append({
                    "type": "replace",
                    "student_word": s_slice[0],
                    "teacher_word": t_slice[0],
                    "is_error": True,
                    "error_type": "minor",
                    "hint": err_hint,
                })
            else:
                major_error_count += 1
                s_str = " ".join(s_slice)
                t_str = " ".join(t_slice)
                err_hint = f"Sai cấu trúc/từ: '{s_str}' → '{t_str}'"
                error_details.append(err_hint)
                diff_tokens.append({
                    "type": "replace",
                    "student_word": s_str,
                    "teacher_word": t_str,
                    "is_error": True,
                    "error_type": "major",
                    "hint": err_hint,
                })
        elif tag == "insert":
            t_slice = t_tokens[j1:j2]
            for t_tok in t_slice:
                if re.match(r"^[^\w\s]$", t_tok):
                    minor_error_count += 1
                    err_hint = f"Thiếu dấu câu '{t_tok}'"
                    error_details.append(err_hint)
                    diff_tokens.append({
                        "type": "missing",
                        "student_word": "",
                        "teacher_word": t_tok,
                        "is_error": True,
                        "error_type": "minor",
                        "hint": err_hint,
                    })
                else:
                    major_error_count += 1
                    err_hint = f"Thiếu từ '{t_tok}'"
                    error_details.append(err_hint)
                    diff_tokens.append({
                        "type": "missing",
                        "student_word": "",
                        "teacher_word": t_tok,
                        "is_error": True,
                        "error_type": "major",
                        "hint": err_hint,
                    })
        elif tag == "delete":
            s_slice = s_tokens[i1:i2]
            for s_tok in s_slice:
                major_error_count += 1
                err_hint = f"Thừa từ '{s_tok}'"
                error_details.append(err_hint)
                diff_tokens.append({
                    "type": "extra",
                    "student_word": s_tok,
                    "teacher_word": "",
                    "is_error": True,
                    "error_type": "major",
                    "hint": err_hint,
                })

    if major_error_count > 0:
        points = Decimal("0.00")
        status = "wrong"
        feedback = f"Chuyển sai so với giáo viên (trừ hết điểm). Các lỗi: {'; '.join(error_details[:3])}."
    elif minor_error_count > 0:
        deduction = Decimal(str(minor_error_count * 0.5))
        points = max(Decimal("0.00"), max_pts - deduction)
        status = "partial" if points > 0 else "wrong"
        feedback = f"Trừ {deduction} điểm do có {minor_error_count} lỗi nhỏ: {'; '.join(error_details)}."
    else:
        points = max_pts
        status = "correct"
        feedback = "Chính xác tuyệt đối! Đạt điểm tối đa."

    if capitalization_hints:
        feedback += f" Gợi ý viết hoa theo đáp án: {'; '.join(capitalization_hints)}."

    if ([token.lower() for token in s_tokens] == [token.lower() for token in t_tokens]
            and re.split(r"\w+|[^\w\s]", student_original) != re.split(r"\w+|[^\w\s]", standard_original)):
        feedback += f" Gợi ý cách đặt khoảng trắng và dấu câu: {t_raw}"

    return {
        "points": points,
        "max_points": float(max_pts),
        "status": status,
        "student_answer": s_raw,
        "standard_answer": t_raw,
        "diff_tokens": diff_tokens,
        "minor_errors": minor_error_count,
        "major_errors": major_error_count,
        "feedback": feedback,
    }


def _normalize_word_form(text):
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def grade_word_form(student_text, standard_text, max_points):
    max_pts = Decimal(str(max_points))
    s_raw = (student_text or "").strip()
    t_raw = (standard_text or "").strip()

    if not s_raw:
        return {
            "points": Decimal("0.00"),
            "max_points": float(max_pts),
            "status": "wrong",
            "student_answer": s_raw,
            "standard_answer": t_raw,
            "feedback": "Chưa nhập đáp án (0 điểm).",
        }

    variants = [v.strip() for v in re.split(r"\s*[/|]\s*", t_raw) if v.strip()]
    normalized_variants = {_normalize_word_form(v) for v in variants} if variants else {_normalize_word_form(t_raw)}

    if _normalize_word_form(s_raw) in normalized_variants:
        return {
            "points": max_pts,
            "max_points": float(max_pts),
            "status": "correct",
            "student_answer": s_raw,
            "standard_answer": t_raw,
            "feedback": "Chính xác! Đạt điểm tối đa.",
        }

    return {
        "points": Decimal("0.00"),
        "max_points": float(max_pts),
        "status": "wrong",
        "student_answer": s_raw,
        "standard_answer": t_raw,
        "feedback": f"Chưa chính xác. Đáp án đúng là: {t_raw}.",
    }
