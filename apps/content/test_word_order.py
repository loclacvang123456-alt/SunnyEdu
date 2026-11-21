from datetime import timedelta
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient, Response
from apps.assignments.services import ConflictError, save_response, start_attempt, submit_attempt
from apps.content.editor_services import clone_version, upsert_question
from apps.content.models import Exam, ExamVersion
from apps.content.services import publish_version
from apps.grading.models import Grade


class WordOrderTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', role='OWNER', display_name='Teacher')
        self.student = User.objects.create_user(username='student', role='STUDENT', display_name='Student')
        self.exam = Exam.objects.create(created_by=self.owner, title='Practice')
        self.version = ExamVersion.objects.create(exam=self.exam, number=1)
        self.payload = {'type':'WORD_ORDER','skill':'WRITING','difficulty':'FOUNDATION','prompt':'Arrange the words', 'max_points':'2.00','topic_tags':['Sentence order'], 'word_tokens':['I','like','the','cat','and','the','dog']}
        self.q, self.version = upsert_question(self.owner, self.version.id, 0, self.payload)

    def create_attempt(self):
        self.version = publish_version(self.version.id, self.version.revision)
        now = timezone.now()
        assignment = Assignment.objects.create(version=self.version,title='Arrange',code='HW-TST123',status='PUBLISHED',opens_at=now-timedelta(hours=1),due_at=now+timedelta(days=1),late_until=now+timedelta(days=2))
        recipient = AssignmentRecipient.objects.create(assignment=assignment,student=self.student)
        return start_attempt(recipient.id,self.student)[0]

    def test_published_version_cannot_be_edited_and_clone_preserves_words(self):
        self.version = publish_version(self.version.id,self.version.revision)
        with self.assertRaises(ValidationError):
            upsert_question(self.owner,self.version.id,self.version.revision,self.payload,self.q.id)
        clone = clone_version(self.owner,self.version.id)
        self.assertEqual(list(clone.questions.first().options.values_list('content',flat=True)),self.payload['word_tokens'])

    def test_duplicate_words_may_swap_and_score_full(self):
        attempt = self.create_attempt()
        options = list(self.q.options.all())
        ids = [str(option.id) for option in options]
        ids[2], ids[5] = ids[5], ids[2]
        response, attempt = save_response(attempt.id,self.q.id,self.student,0,ordered_option_ids=ids)
        submit_attempt(attempt.id,self.student,attempt.revision,uuid4())
        self.assertEqual(Grade.objects.get(response=response).points,2)

    def test_wrong_and_partial_order_score_zero(self):
        attempt = self.create_attempt()
        options = list(self.q.options.all())
        ids = [str(o.id) for o in options[:2]]
        response, attempt = save_response(attempt.id,self.q.id,self.student,0,ordered_option_ids=ids)
        submit_attempt(attempt.id,self.student,attempt.revision,uuid4())
        self.assertEqual(Grade.objects.get(response=response).points,0)

    def test_reject_foreign_or_repeated_ids_and_stale_revision(self):
        attempt = self.create_attempt()
        option = str(self.q.options.first().id)
        for ids in ([option,option],[str(uuid4())]):
            with self.assertRaises(ValidationError):
                save_response(attempt.id,self.q.id,self.student,0,ordered_option_ids=ids)
        save_response(attempt.id,self.q.id,self.student,0,ordered_option_ids=[option])
        with self.assertRaises(ConflictError):
            save_response(attempt.id,self.q.id,self.student,0,ordered_option_ids=[])

    def test_serializer_uses_stable_per_attempt_order_and_no_answer_key(self):
        from apps.accounts.services import initialize_session
        attempt = self.create_attempt()
        self.client.force_login(self.student)
        session = self.client.session
        now = timezone.now().isoformat()
        session['issued_at'] = session['last_activity'] = now
        session['auth_epoch'] = self.student.auth_epoch
        session['remember_device'] = False
        session.save()
        url = f'/api/v1/attempts/{attempt.id}/'
        first = self.client.get(url)
        self.assertEqual(first.status_code,200)
        q = first.json()['data']['questions'][0]
        self.assertEqual(q['type'],'WORD_ORDER')
        self.assertEqual(q['ordered_option_ids'],[])
        self.assertNotEqual([option['content'] for option in q['options']],self.payload['word_tokens'])
        self.assertEqual(q['options'],self.client.get(url).json()['data']['questions'][0]['options'])
        for option in q['options']:
            self.assertEqual(set(option),{'id','content'})
        self.assertNotIn('answer_keys',first.content.decode())

    def test_http_saves_word_order_without_revealing_answer(self):
        import json
        from apps.accounts.services import rotate_code
        attempt = self.create_attempt()
        code = rotate_code(self.student, actor=self.owner)
        client = self.client_class(enforce_csrf_checks=True)
        client.get('/api/v1/auth/csrf/')
        csrf = client.cookies['csrftoken'].value
        login = client.post('/api/v1/auth/student-login/', data=json.dumps({'code':code}), content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(login.status_code, 200)
        csrf = client.cookies['csrftoken'].value
        url = f'/api/v1/attempts/{attempt.id}/responses/{self.q.id}/'
        ids = [str(o.id) for o in self.q.options.all()]
        result = client.put(url, data=json.dumps({'expected_revision':0,'ordered_option_ids':ids}), content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(result.status_code,200)
        data = client.get(f'/api/v1/attempts/{attempt.id}/').json()['data']['questions'][0]
        self.assertEqual(data['ordered_option_ids'],ids)
        self.assertNotIn('correct_order',data)
        self.assertEqual(Response.objects.get(attempt=attempt,question=self.q).ordered_option_ids,ids)
