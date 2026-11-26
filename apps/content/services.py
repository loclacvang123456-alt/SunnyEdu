import csv
import io
import zipfile
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Asset, AnswerKeyOption, Exam, ExamVersion, MatchKey, Passage, Question, QuestionOption, QuestionTag, RubricCriterion, Tag

FIELDS = ("position", "type", "skill", "difficulty", "prompt", "max_points", "option_a", "option_b", "option_c", "option_d", "option_e", "option_f", "correct_options", "passage_ref", "passage_text", "audio_asset_id", "transcript", "topic_tags", "error_tags", "explanation", "image_url")
LEVELS = {"0": "Không có bằng chứng đáp ứng", "1": "Đáp ứng ít", "2": "Đáp ứng một phần", "3": "Đáp ứng phần lớn", "4": "Đáp ứng đầy đủ"}
RUBRICS = {"TEXT": [("task", "Hoàn thành yêu cầu"), ("organization", "Tổ chức ý"), ("vocabulary", "Từ vựng"), ("grammar", "Ngữ pháp")], "AUDIO": [("task", "Nội dung"), ("fluency", "Độ trôi chảy"), ("language", "Từ vựng và ngữ pháp"), ("pronunciation", "Phát âm dễ hiểu")]}


def _extract_import_stress(options, answer):
    if options[0] and not any(options[1:]) and '-' in options[0]:
        syllables = [s.strip() for s in options[0].split('-') if s.strip()]
    else:
        count = sum(bool(x) for x in options)
        if any(not v for v in options[:count]):
            raise ValueError('Âm tiết phải liên tục từ A')
        syllables = [v.strip() for v in options[:count]]
    if not 2 <= len(syllables) <= 10 or any(not s or len(s) > 80 or any(c.isspace() for c in s) for s in syllables):
        raise ValueError('Trọng âm cần 2 đến 10 âm tiết (không chứa khoảng trắng)')
    if len(answer) != 1:
        raise ValueError('Trọng âm cần đúng 1 đáp án')
    token = answer[0].strip().upper()
    if token.isdigit():
        idx = int(token)
    elif len(token) == 1 and 'A' <= token <= 'Z':
        idx = ord(token) - ord('A') + 1
    else:
        raise ValueError('Đáp án trọng âm không hợp lệ')
    if not 1 <= idx <= len(syllables):
        raise ValueError('Đáp án trọng âm vượt quá số âm tiết')
    return syllables, idx


def _extract_import_word_order(options, answer):
    if answer:
        raise ValueError('Câu sắp xếp từ không điền cột correct_options')
    if options[0] and not any(options[1:]) and ('|' in options[0] or ' ' in options[0]):
        raw = options[0].split('|') if '|' in options[0] else options[0].split()
        tokens = [t.strip() for t in raw if t.strip()]
    else:
        count = sum(bool(x) for x in options)
        if any(not v for v in options[:count]):
            raise ValueError('Các từ phải liên tục từ A')
        tokens = [v.strip() for v in options[:count]]
    if not 2 <= len(tokens) <= 20 or any(not t or len(t) > 80 for t in tokens):
        raise ValueError('Câu sắp xếp cần từ 2 đến 20 từ/cụm từ')
    return tokens


def parse_questions(data, filename):
    if len(data) > 2 * 1024 * 1024:
        raise ValidationError("Tệp vượt quá 2 MiB.")
    if filename.lower().endswith('.csv'):
        try:
            reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''))
            headers = [h.strip() for h in (reader.fieldnames or [])]
            if headers[:len(FIELDS)] == list(FIELDS):
                active_fields = list(FIELDS)
            elif headers[:len(FIELDS)-1] == list(FIELDS[:-1]):
                active_fields = list(FIELDS[:-1])
            else:
                raise ValidationError("Cột CSV không khớp mẫu.")
            rows = []
            for r in reader:
                if any((r.get(k) or '').strip() for k in active_fields):
                    rows.append({k: (r.get(k) or '').strip() for k in FIELDS})
        except UnicodeDecodeError as e:
            raise ValidationError("CSV phải dùng UTF-8.") from e
    elif filename.lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                members = z.infolist()
                if len(members) > 100 or sum(m.file_size for m in members) > 10 * 1024 * 1024 or any('vbaProject' in m.filename or 'externalLinks/' in m.filename for m in members):
                    raise ValidationError("XLSX không an toàn hoặc quá lớn.")
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
            if workbook.sheetnames != ['questions']:
                raise ValidationError("XLSX phải có một sheet questions.")
            sheet = workbook['questions']
            values = sheet.iter_rows()
            first = next(values, None)
            first_vals = [c.value for c in first] if first else []
            if first_vals[:len(FIELDS)] == list(FIELDS):
                active_fields = list(FIELDS)
            elif first_vals[:len(FIELDS)-1] == list(FIELDS[:-1]):
                active_fields = list(FIELDS[:-1])
            else:
                raise ValidationError("Cột XLSX không khớp mẫu.")
            rows = []
            for cells in values:
                cell_list = list(cells)
                if any(getattr(c, 'data_type', None) == 'f' for c in cell_list):
                    raise ValidationError("Không nhận công thức XLSX.")
                core_cells = (cell_list + [None] * max(0, len(active_fields) - len(cell_list)))[:len(active_fields)]
                if all(c is None or c.value is None or str(c.value).strip() == '' for c in core_cells):
                    continue
                row_dict = {key: '' if (c is None or c.value is None) else str(c.value) for key, c in zip(active_fields, core_cells)}
                if 'image_url' not in row_dict:
                    row_dict['image_url'] = ''
                rows.append(row_dict)
            workbook.close()
        except (zipfile.BadZipFile, KeyError, ValueError) as e:
            raise ValidationError("XLSX không hợp lệ.") from e
    else:
        raise ValidationError("Chỉ nhận CSV hoặc XLSX.")
    if not 1 <= len(rows) <= 100:
        raise ValidationError("Đề cần từ 1 đến 100 câu.")
    if sum(len(str(v).encode('utf-8')) for r in rows for k in FIELDS if (v := r.get(k)) is not None) > 500 * 1024:
        raise ValidationError("Nội dung vượt quá 500 KiB.")
    errors, passages = [], {}
    for i, row in enumerate(rows, start=1):
        try:
            if None in row or any(row.get(k) is None for k in FIELDS):
                raise ValueError('Sai số cột')
            row = {k: (row.get(k) or '').strip() for k in FIELDS}
            if not row['position']:
                row['position'] = str(i)
            if not row['max_points']:
                row['max_points'] = '1.00'
            row['difficulty'] = (row['difficulty'] or 'STANDARD').upper()
            options = [row['option_'+c.lower()] for c in 'ABCDEF']
            filled_opts = [x for x in options if x]
            q_type = row['type'].upper()
            if not q_type:
                prompt_low = row['prompt'].lower()
                if options[0] and not any(options[1:]):
                    if '|' in options[0] and not row['correct_options']:
                        q_type = 'WORD_ORDER'
                    elif '-' in options[0] and row['correct_options']:
                        q_type = 'STRESS_CHOICE'
                    elif 'dùng dạng đúng của từ trong ngoặc' in prompt_low or 'word form' in prompt_low:
                        q_type = 'WORD_FORM'
                    else:
                        q_type = 'SENTENCE_TRANSFORM'
                elif len(filled_opts) >= 2:
                    if '|' in row['correct_options']:
                        q_type = 'MULTIPLE_CHOICE'
                    elif 'trọng âm' in prompt_low or 'stress' in prompt_low:
                        q_type = 'STRESS_CHOICE'
                    else:
                        q_type = 'SINGLE_CHOICE'
                elif any(k in prompt_low for k in ('ghi âm', 'thu âm', 'nói', 'speaking', 'record')):
                    q_type = 'AUDIO'
                else:
                    q_type = 'TEXT'
            row['type'] = q_type
            skill = row['skill'].upper()
            if not skill:
                if row['audio_asset_id']:
                    skill = 'LISTENING'
                elif q_type == 'AUDIO':
                    skill = 'SPEAKING'
                elif q_type in ('TEXT', 'WORD_ORDER', 'SENTENCE_TRANSFORM', 'WORD_FORM'):
                    skill = 'WRITING'
                else:
                    skill = 'READING'
            row['skill'] = skill
            rows[i-1] = row
            if int(row['position']) != i:
                raise ValueError('Thứ tự phải liên tục từ 1')
            allowed = {
                'SINGLE_CHOICE': {'READING', 'LISTENING'},
                'MULTIPLE_CHOICE': {'READING', 'LISTENING'},
                'STRESS_CHOICE': {'READING', 'LISTENING'},
                'WORD_ORDER': {'READING', 'WRITING'},
                'SENTENCE_TRANSFORM': {'READING', 'WRITING'},
                'WORD_FORM': {'READING', 'WRITING'},
                'TEXT': {'WRITING'},
                'AUDIO': {'SPEAKING'},
            }
            if row['skill'] not in allowed.get(row['type'], set()) or row['difficulty'] not in Question.Difficulty.values:
                raise ValueError('Loại câu, kỹ năng hoặc độ khó không hợp lệ')
            points = Decimal(row['max_points'])
            if not points.is_finite() or not Decimal('.01') <= points <= Decimal('100') or points.as_tuple().exponent < -2:
                raise ValueError('Điểm không hợp lệ')
            if not 1 <= len(row['prompt']) <= 10000:
                raise ValueError('Nội dung câu không hợp lệ')
            answer = row['correct_options'].split('|') if row['correct_options'] else []
            if row['type'] in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE'):
                count = sum(bool(x) for x in options)
                if not 2 <= count <= 6 or any(not v for v in options[:count]) or any(len(v)>2000 for v in options):
                    raise ValueError('Lựa chọn phải liên tục từ A, từ 2 đến 6')
                if len(set(answer)) != len(answer) or not set(answer) <= set('ABCDEF'[:count]) or (len(answer) != 1 if row['type']=='SINGLE_CHOICE' else len(answer)<2):
                    raise ValueError('Đáp án không hợp lệ')
            elif row['type'] == 'STRESS_CHOICE':
                _extract_import_stress(options, answer)
            elif row['type'] == 'WORD_ORDER':
                _extract_import_word_order(options, answer)
            elif row['type'] in ('SENTENCE_TRANSFORM', 'WORD_FORM'):
                if not options[0] or len(options[0]) > 2000 or any(options[1:]) or (answer and answer != ['A']):
                    raise ValueError('Câu viết lại / Word form cần điền đáp án chuẩn ở option_a')
                if not row['correct_options']:
                    row['correct_options'] = 'A'
            elif any(options) or answer:
                raise ValueError('Tự luận và ghi âm không có lựa chọn')
            raw_topics = [x.strip() for x in row['topic_tags'].split('|')] if row['topic_tags'] else []
            raw_errors = [x.strip() for x in row['error_tags'].split('|')] if row['error_tags'] else []
            if any(not x or len(x) > 100 for x in raw_topics + raw_errors):
                raise ValueError('Chủ đề hoặc lỗi không hợp lệ')
            ref = row['passage_ref']
            if len(ref)>40 or len(row['passage_text'])>20000 or (not ref and any(row[k] for k in ('passage_text','audio_asset_id','transcript'))):
                raise ValueError('Tài liệu không hợp lệ')
            value = tuple(row[k] for k in ('passage_text','audio_asset_id','transcript'))
            if ref and (not any(value[:2]) or (ref in passages and passages[ref] != value)):
                raise ValueError('Tài liệu trống hoặc không thống nhất')
            if ref:
                passages[ref] = value
            if row['skill']=='LISTENING' and (not ref or not row['audio_asset_id']):
                raise ValueError('Listening cần tài liệu audio')
        except (ValueError, InvalidOperation) as e:
            errors.append(f'Dòng {i+1}: {e}')
    if errors:
        raise ValidationError(errors)
    return rows


@transaction.atomic
def create_imported_exam(owner, title, rows, exam=None):
    if not title or len(title)>200:
        raise ValidationError('Tên đề không hợp lệ.')
    if exam is None:
        exam = Exam.objects.create(title=title, created_by=owner)
    else:
        exam = Exam.objects.select_for_update().get(pk=exam.pk, created_by=owner)
    latest = exam.versions.order_by('-number').first()
    version = ExamVersion.objects.create(exam=exam, number=latest.number+1 if latest else 1)
    passages = {}
    for row in rows:
        ref = row['passage_ref']
        if ref and ref not in passages:
            audio = None
            if row['audio_asset_id']:
                try:
                    audio = Asset.objects.select_for_update().get(pk=row['audio_asset_id'], uploaded_by=owner, purpose=Asset.Purpose.PROMPT_AUDIO, status=Asset.Status.READY)
                except (Asset.DoesNotExist, ValueError) as e:
                    raise ValidationError('Tệp nghe không tồn tại hoặc chưa sẵn sàng.') from e
            passages[ref] = Passage.objects.create(version=version, ref=ref, text_body=row['passage_text'], audio_asset=audio, transcript=row['transcript'])
        question = Question.objects.create(version=version, position=int(row['position']), type=row['type'], skill=row['skill'], difficulty=row['difficulty'], prompt=row['prompt'], max_points=Decimal(row['max_points']), passage=passages.get(ref), explanation=row['explanation'], image_url=row.get('image_url', ''))
        options = [row['option_'+c.lower()] for c in 'ABCDEF']
        answer = row['correct_options'].split('|') if row['correct_options'] else []
        if row['type'] == 'STRESS_CHOICE':
            syllables, stress_idx = _extract_import_stress(options, answer)
            for idx, syl in enumerate(syllables, 1):
                option = QuestionOption.objects.create(question=question, key=chr(ord('A') + idx - 1), position=idx, content=syl)
                if idx == stress_idx:
                    AnswerKeyOption.objects.create(question=question, option=option)
        elif row['type'] == 'WORD_ORDER':
            for idx, tok in enumerate(_extract_import_word_order(options, answer), 1):
                QuestionOption.objects.create(question=question, key=chr(ord('A') + idx - 1), position=idx, content=tok)
        elif row['type'] in ('SENTENCE_TRANSFORM', 'WORD_FORM'):
            option = QuestionOption.objects.create(question=question, key='A', position=1, content=row['option_a'])
            AnswerKeyOption.objects.create(question=question, option=option)
        else:
            for idx, key in enumerate('ABCDEF', 1):
                content = row['option_'+key.lower()]
                if content:
                    option = QuestionOption.objects.create(question=question, key=key, position=idx, content=content)
                    if key in answer:
                        AnswerKeyOption.objects.create(question=question, option=option)
        from .auto_tagging import apply_auto_tags_to_question
        for kind, field in [('TOPIC', 'topic_tags'), ('ERROR', 'error_tags')]:
            for name in dict.fromkeys(x.strip() for x in row[field].split('|') if x.strip()):
                tag, _ = Tag.objects.get_or_create(kind=kind, skill=row['skill'], name=name)
                if tag.archived_at:
                    raise ValidationError('Tag đã lưu trữ, hãy chọn tag khác.')
                QuestionTag.objects.get_or_create(question=question, tag=tag)
        apply_auto_tags_to_question(question, title_context=title)
        for idx, (key, label) in enumerate(RUBRICS.get(row['type'], []), 1):
            RubricCriterion.objects.create(question=question, key=key, position=idx, label=label, level_descriptions=LEVELS)
    return version


@transaction.atomic
def publish_version(version_id, expected_revision):
    version = ExamVersion.objects.select_for_update().get(pk=version_id)
    if version.status != ExamVersion.Status.DRAFT or version.revision != expected_revision:
        raise ValidationError('Phiên bản đã thay đổi hoặc không còn là bản nháp.')
    from .auto_tagging import sync_version_and_exercise_auto_tags
    sync_version_and_exercise_auto_tags(version)
    questions = list(version.questions.all().prefetch_related('options', 'answer_keys', 'criteria', 'question_tags__tag', 'passage__audio_asset'))
    if not 1 <= len(questions) <= 100:
        raise ValidationError('Đề cần từ 1 đến 100 câu.')
    for q in questions:
        options, answers = list(q.options.all()), list(q.answer_keys.all())
        if q.passage and q.passage.version_id != version.id:
            raise ValidationError('Tài liệu không thuộc phiên bản đề.')
        if q.skill == 'LISTENING' and (not q.passage or not q.passage.audio_asset or q.passage.audio_asset.status != Asset.Status.READY):
            raise ValidationError('Listening cần tài liệu audio sẵn sàng.')
        if not any(t.tag.kind == 'TOPIC' and t.tag.skill == q.skill and not t.tag.archived_at for t in q.question_tags.all()):
            raise ValidationError('Mỗi câu cần ít nhất một chủ đề phù hợp.')
        if any(a.option.question_id != q.id for a in answers):
            raise ValidationError('Đáp án không thuộc câu.')
        if q.type in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE'):
            if not 2 <= len(options) <= 6 or (len(answers) != 1 if q.type == 'SINGLE_CHOICE' else len(answers) < 2):
                raise ValidationError('Lựa chọn hoặc đáp án không hợp lệ.')
        elif q.type == 'MATCH_IMAGE':
            images = list(q.match_images.select_related('image_asset', 'answer_key__word'))
            words = list(q.match_words.all())
            if not 2 <= len(images) <= 6 or len(words) != len(images) or len({w.text.casefold() for w in words}) != len(words):
                raise ValidationError('Câu nối tranh cần 2 đến 6 cặp tranh và từ khác nhau.')
            try:
                targets = [image.answer_key.word for image in images]
            except MatchKey.DoesNotExist as exc:
                raise ValidationError('Thiếu đáp án nối tranh.') from exc
            if any(image.image_asset.purpose != Asset.Purpose.PROMPT_IMAGE or image.image_asset.status != Asset.Status.READY or image.image_asset.uploaded_by_id != version.exam.created_by_id for image in images) or {w.id for w in targets} != {w.id for w in words}:
                raise ValidationError('Ảnh hoặc đáp án nối tranh không hợp lệ.')
        elif q.type == 'STRESS_CHOICE':
            if not 2 <= len(options) <= 10 or len(answers) != 1 or any(not o.content.strip() or len(o.content) > 80 or any(c.isspace() for c in o.content) for o in options):
                raise ValidationError('Câu trọng âm cần 2 đến 10 âm tiết và đúng một đáp án.')
        elif q.type == 'WORD_ORDER':
            if not 2 <= len(options) <= 20 or any(not o.content.strip() or len(o.content) > 80 for o in options) or answers:
                raise ValidationError('Câu sắp xếp cần 2 đến 20 ô từ hợp lệ.')
        elif q.type in ('SENTENCE_TRANSFORM', 'WORD_FORM'):
            if len(options) != 1 or not options[0].content.strip():
                raise ValidationError('Câu đổi câu / điền dạng từ cần một đáp án chuẩn của giáo viên.')
        else:
            criteria = list(q.criteria.all())
            if len(criteria) != 4 or any(set(c.level_descriptions) != {'0','1','2','3','4'} or not all(c.level_descriptions.values()) for c in criteria):
                raise ValidationError('Cần bốn tiêu chí với đủ năm mức.')
    version.status = ExamVersion.Status.PUBLISHED
    version.published_at = timezone.now()
    version.revision += 1
    version.save(update_fields=['status', 'published_at', 'revision', 'updated_at'])
    return version


def preview_question_import(owner, data, filename):
    import hashlib
    from datetime import timedelta
    from .models import ImportBatch
    rows = parse_questions(data, filename)
    return ImportBatch.objects.create(owner=owner, payload_json=rows, source_digest=hashlib.sha256(data).hexdigest(), expires_at=timezone.now()+timedelta(hours=24))


@transaction.atomic
def commit_question_import(owner, batch_id, expected_digest, title, exam=None):
    from .models import ImportBatch
    batch = ImportBatch.objects.select_for_update().get(pk=batch_id, owner=owner, kind='QUESTIONS')
    if batch.source_digest != expected_digest:
        raise ValidationError('Nội dung tệp đã thay đổi.')
    if batch.status == ImportBatch.Status.COMMITTED:
        return batch.committed_version
    if batch.status != ImportBatch.Status.PREVIEW or batch.expires_at <= timezone.now():
        raise ValidationError('Bản xem trước đã hết hạn.')
    version = create_imported_exam(owner, title, batch.payload_json, exam)
    batch.status = ImportBatch.Status.COMMITTED
    batch.committed_version = version
    batch.save(update_fields=['status', 'committed_version', 'updated_at'])
    return version
