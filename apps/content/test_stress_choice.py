from datetime import timedelta
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.assignments.services import save_response, start_attempt, submit_attempt
from apps.content.editor_services import clone_version, upsert_question
from apps.content.models import Exam, ExamVersion
from apps.content.services import publish_version
from apps.grading.models import Grade


class StressChoiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', role='OWNER', display_name='Teacher')
        self.student = User.objects.create_user(username='student', role='STUDENT', display_name='Student')
        self.exam = Exam.objects.create(created_by=self.owner, title='Stress')
        self.version = ExamVersion.objects.create(exam=self.exam, number=1)
        self.payload = {'type':'STRESS_CHOICE','skill':'READING','difficulty':'FOUNDATION','prompt':'Chọn trọng âm', 'max_points':'2.00','topic_tags':['Word stress'], 'stress_syllables':['el','e','phant'], 'correct_syllable_index':1}
        self.q, self.version = upsert_question(self.owner, self.version.id, 0, self.payload)

    def make_attempt(self):
        self.version = publish_version(self.version.id,self.version.revision)
        now = timezone.now()
        assignment = Assignment.objects.create(version=self.version,title='Stress',code='HW-STR123',status='PUBLISHED',opens_at=now-timedelta(hours=1),due_at=now+timedelta(days=1),late_until=now+timedelta(days=2))
        recipient = AssignmentRecipient.objects.create(assignment=assignment,student=self.student)
        return start_attempt(recipient.id,self.student)[0]

    def test_editor_and_clone_retain_syllable_and_correct_answer(self):
        self.assertEqual(list(self.q.options.values_list('content',flat=True)), ['el','e','phant'])
        self.assertEqual(self.q.answer_keys.get().option.content,'el')
        self.version = publish_version(self.version.id,self.version.revision)
        with self.assertRaises(ValidationError):
            upsert_question(self.owner,self.version.id,self.version.revision,self.payload,self.q.id)
        clone = clone_version(self.owner,self.version.id)
        self.assertEqual(clone.questions.first().answer_keys.get().option.content,'el')

    def test_score_correct_and_reject_multiple_or_foreign(self):
        attempt = self.make_attempt()
        options = list(self.q.options.all())
        with self.assertRaises(ValidationError):
            save_response(attempt.id,self.q.id,self.student,0,option_ids=[str(options[0].id),str(options[1].id)])
        with self.assertRaises(ValidationError):
            save_response(attempt.id,self.q.id,self.student,0,option_ids=[str(uuid4())])
        response, attempt = save_response(attempt.id,self.q.id,self.student,0,option_ids=[str(options[0].id)])
        submit_attempt(attempt.id,self.student,attempt.revision,uuid4())
        self.assertEqual(Grade.objects.get(response=response).points,2)

    def test_wrong_and_blank_score_zero(self):
        attempt = self.make_attempt()
        response, attempt = save_response(attempt.id,self.q.id,self.student,0,option_ids=[str(self.q.options.all()[1].id)])
        submit_attempt(attempt.id,self.student,attempt.revision,uuid4())
        self.assertEqual(Grade.objects.get(response=response).points,0)

    def test_api_never_discloses_correct_stress(self):
        attempt = self.make_attempt()
        self.client.force_login(self.student)
        session = self.client.session
        now = timezone.now().isoformat()
        session['issued_at'] = session['last_activity'] = now
        session['auth_epoch'] = self.student.auth_epoch
        session['remember_device'] = False
        session.save()
        result = self.client.get(f'/api/v1/attempts/{attempt.id}/')
        self.assertEqual(result.status_code,200)
        question = result.json()['data']['questions'][0]
        self.assertEqual(question['type'],'STRESS_CHOICE')
        self.assertEqual([o['content'] for o in question['options']],['el','e','phant'])
        self.assertTrue(all(set(o)=={'id','content'} for o in question['options']))
        self.assertNotIn('correct_syllable_index',question)
        self.assertNotIn('answer_keys',result.content.decode())

    def test_reject_invalid_syllables_and_answer(self):
        for patch in ({'correct_syllable_index':0},{'correct_syllable_index':4},{'stress_syllables':['one']},{'stress_syllables':['two words','no']}):
            bad = {**self.payload, **patch}
            with self.assertRaises(ValidationError):
                upsert_question(self.owner,self.version.id,self.version.revision,bad)
