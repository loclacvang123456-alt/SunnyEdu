from datetime import timedelta
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.assignments.services import save_response, start_attempt, submit_attempt
from apps.content.editor_services import clone_version, upsert_question
from apps.content.models import Asset, Exam, ExamVersion, MatchImage, MatchWord
from apps.content.services import publish_version
from apps.grading.models import Grade


class MatchImageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner',role='OWNER',display_name='Teacher')
        self.student = User.objects.create_user(username='student',role='STUDENT',display_name='Student')
        self.other = User.objects.create_user(username='other',role='STUDENT',display_name='Other')
        self.exam = Exam.objects.create(created_by=self.owner,title='Matching')
        self.version = ExamVersion.objects.create(exam=self.exam,number=1)
        self.assets = [Asset.objects.create(uploaded_by=self.owner,purpose='PROMPT_IMAGE',object_key=f'test/{i}',status='READY',bytes=42,detected_mime='image/png') for i in range(2)]
        self.data = {'type':'MATCH_IMAGE','skill':'READING','difficulty':'FOUNDATION','prompt':'Nối tranh và từ','max_points':'2.00','topic_tags':['Animals'],'match_pairs':[{'image_asset_id':str(self.assets[0].id),'word':'cat'},{'image_asset_id':str(self.assets[1].id),'word':'dog'}]}
        self.q,self.version=upsert_question(self.owner,self.version.id,0,self.data)

    def make_attempt(self):
        self.version=publish_version(self.version.id,self.version.revision)
        now=timezone.now()
        a=Assignment.objects.create(version=self.version,title='Match',code='HW-MATCH1',status='PUBLISHED',opens_at=now-timedelta(hours=1),due_at=now+timedelta(days=1),late_until=now+timedelta(days=2))
        r=AssignmentRecipient.objects.create(assignment=a,student=self.student)
        return start_attempt(r.id,self.student)[0]

    def test_clone_publish_and_draft_immutability(self):
        self.version=publish_version(self.version.id,self.version.revision)
        with self.assertRaises(ValidationError): upsert_question(self.owner,self.version.id,self.version.revision,self.data,self.q.id)
        q=clone_version(self.owner,self.version.id).questions.get()
        self.assertEqual([(i.image_asset_id,i.answer_key.word.text) for i in q.match_images.all()],[(a.id,w) for a,w in zip(self.assets,['cat','dog'])])

    def test_exact_mapping_scores_full_even_if_pairs_reordered(self):
        attempt=self.make_attempt()
        images=list(self.q.match_images.select_related('answer_key'))
        pairs=[{'image_id':str(i.id),'word_id':str(i.answer_key.word_id)} for i in reversed(images)]
        response,attempt=save_response(attempt.id,self.q.id,self.student,0,match_pairs=pairs)
        submit_attempt(attempt.id,self.student,attempt.revision,uuid4())
        self.assertEqual(Grade.objects.get(response=response).points,2)

    def test_partial_wrong_and_blank_are_zero(self):
        attempt=self.make_attempt()
        img=self.q.match_images.select_related('answer_key').first()
        response,attempt=save_response(attempt.id,self.q.id,self.student,0,match_pairs=[{'image_id':str(img.id),'word_id':str(img.answer_key.word_id)}])
        submit_attempt(attempt.id,self.student,attempt.revision,uuid4())
        self.assertEqual(Grade.objects.get(response=response).points,0)

    def test_reject_cross_question_or_duplicate_ids(self):
        attempt=self.make_attempt()
        img=self.q.match_images.first(); word=self.q.match_words.first()
        pair={'image_id':str(img.id),'word_id':str(word.id)}
        for bad in ([pair,pair],[{'image_id':str(uuid4()),'word_id':str(word.id)}],[{'image_id':str(img.id),'word_id':str(uuid4())}]):
            with self.assertRaises(ValidationError): save_response(attempt.id,self.q.id,self.student,0,match_pairs=bad)

    def test_student_serializer_never_exposes_keys(self):
        attempt=self.make_attempt()
        self.client.force_login(self.student)
        s=self.client.session; now=timezone.now().isoformat();s['issued_at']=s['last_activity']=now;s['auth_epoch']=self.student.auth_epoch;s['remember_device']=False;s.save()
        data=self.client.get(f'/api/v1/attempts/{attempt.id}/').json()['data']['questions'][0]
        self.assertEqual(set(data['match_images'][0]),{'id','url'})
        self.assertEqual(set(data['match_words'][0]),{'id','text'})
        self.assertEqual(data['match_pairs'],[])
        self.assertNotIn('answer_key',str(data))
        self.assertEqual(self.client.get(f'/api/v1/attempts/{attempt.id}/').json()['data']['questions'][0]['match_images'],data['match_images'])

    def test_other_users_asset_and_duplicate_words_rejected(self):
        asset=Asset.objects.create(uploaded_by=self.other,purpose='PROMPT_IMAGE',object_key='other/test',status='READY',bytes=4,detected_mime='image/png')
        for pairs in ([{'image_asset_id':str(self.assets[0].id),'word':'cat'},{'image_asset_id':str(asset.id),'word':'dog'}],[{'image_asset_id':str(self.assets[0].id),'word':'Cat'},{'image_asset_id':str(self.assets[1].id),'word':'cat'}]):
            with self.assertRaises(ValidationError): upsert_question(self.owner,self.version.id,self.version.revision,{**self.data,'match_pairs':pairs})
