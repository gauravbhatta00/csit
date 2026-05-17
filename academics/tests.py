from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Notification
from .models import (
    Discussion,
    AnswerContribution,
    MockTest,
    MockTestAnswer,
    MockTestQuestion,
    MockTestResult,
    Question,
    Semester,
    Subject,
    Year,
)


User = get_user_model()


class AcademicApiTests(APITestCase):
    def setUp(self):
        self.semester = Semester.objects.create(name='Semester 1')
        self.subject = Subject.objects.create(
            semester=self.semester,
            name='Statistics',
        )
        self.year = Year.objects.create(subject=self.subject, year='2080')

    def test_question_answers_are_visible_without_login(self):
        Question.objects.create(
            year=self.year,
            question_text='Define mean.',
            answer_text='Mean is the arithmetic average.',
            marks='2',
        )

        response = self.client.get(
            f'/api/subjects/{self.subject.slug}/questions/{self.year.year}/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['answer_text'], 'Mean is the arithmetic average.')

    def test_only_approved_contributions_are_visible_with_questions(self):
        contributor = User.objects.create_user(username='helper', password='pass12345')
        question = Question.objects.create(
            year=self.year,
            question_text='Define variance.',
            answer_text='Variance measures spread.',
            marks='2',
        )
        AnswerContribution.objects.create(
            question=question,
            user=contributor,
            answer_text='Pending student answer.',
        )
        approved = AnswerContribution.objects.create(
            question=question,
            user=contributor,
            answer_text='Approved student answer.',
            status=AnswerContribution.STATUS_APPROVED,
        )

        response = self.client.get(
            f'/api/subjects/{self.subject.slug}/questions/{self.year.year}/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data[0]['approved_contributions']), 1)
        self.assertEqual(
            response.data[0]['approved_contributions'][0]['id'],
            approved.id,
        )

    def test_authenticated_user_can_submit_pending_answer_contribution(self):
        user = User.objects.create_user(username='student-two', password='pass12345')
        question = Question.objects.create(
            year=self.year,
            question_text='Define median.',
            answer_text='Median is the middle value.',
            marks='2',
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            f'/api/questions/{question.id}/contributions/',
            {'answer_text': 'Median splits ordered data in half.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], AnswerContribution.STATUS_PENDING)
        contribution = AnswerContribution.objects.get()
        self.assertEqual(contribution.user, user)
        self.assertEqual(contribution.question, question)

    def test_authenticated_user_can_submit_image_only_answer_contribution(self):
        user = User.objects.create_user(username='diagram-student', password='pass12345')
        question = Question.objects.create(
            year=self.year,
            question_text='Draw a normal distribution curve.',
            answer_text='A bell-shaped curve.',
            marks='2',
        )
        image = SimpleUploadedFile(
            'curve.gif',
            (
                b'GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00'
                b'\xff\xff\xff!\xf9\x04\x01\x00\x00\x01\x00,'
                b'\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;'
            ),
            content_type='image/gif',
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            f'/api/questions/{question.id}/contributions/',
            {'image': image},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        contribution = AnswerContribution.objects.get()
        self.assertTrue(contribution.image.name.startswith('answer_contributions/'))

    def test_answer_contribution_rejects_invalid_image_upload(self):
        user = User.objects.create_user(username='bad-upload', password='pass12345')
        question = Question.objects.create(
            year=self.year,
            question_text='Explain skewness.',
            answer_text='Skewness measures asymmetry.',
            marks='2',
        )
        invalid_image = SimpleUploadedFile(
            'not-an-image.png',
            b'not really an image',
            content_type='image/png',
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            f'/api/questions/{question.id}/contributions/',
            {'image': invalid_image},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Upload a valid image file.')

    def test_subject_questions_can_be_loaded_by_subject_id(self):
        Question.objects.create(
            year=self.year,
            question_text='Define mode.',
            answer_text='Mode is the most frequent value.',
            marks='2',
        )

        response = self.client.get(
            f'/api/subjects/{self.subject.id}/questions/{self.year.year}/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['question_text'], 'Define mode.')

    def test_semester_subjects_can_be_loaded_by_semester_id(self):
        response = self.client.get(f'/api/semesters/{self.semester.id}/subjects/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['id'], self.subject.id)

    def test_subject_detail_can_be_loaded_by_slug_and_id(self):
        slug_response = self.client.get(f'/api/subjects/{self.subject.slug}/')
        id_response = self.client.get(f'/api/subjects/{self.subject.id}/')

        self.assertEqual(slug_response.status_code, status.HTTP_200_OK)
        self.assertEqual(id_response.status_code, status.HTTP_200_OK)
        self.assertEqual(slug_response.data['id'], self.subject.id)
        self.assertEqual(id_response.data['slug'], self.subject.slug)

    def test_mock_test_submit_scores_and_stores_answer_review(self):
        user = User.objects.create_user(username='tester', password='pass12345')
        self.client.force_authenticate(user=user)
        mock_test = MockTest.objects.create(
            subject=self.subject,
            title='Stats basics',
            total_marks=3,
        )
        first_question = MockTestQuestion.objects.create(
            mock_test=mock_test,
            question_text='2 + 2?',
            option_a='4',
            option_b='3',
            option_c='2',
            option_d='1',
            correct_option='A',
            marks=1,
        )
        second_question = MockTestQuestion.objects.create(
            mock_test=mock_test,
            question_text='5 - 3?',
            option_a='1',
            option_b='2',
            option_c='3',
            option_d='4',
            correct_option='B',
            marks=2,
        )

        response = self.client.post(
            f'/api/mock-tests/{mock_test.id}/submit/',
            {'answers': {str(first_question.id): 'A'}},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['score'], 1)
        self.assertEqual(response.data['total_marks'], 3)
        result = MockTestResult.objects.get(id=response.data['result_id'])
        self.assertEqual(result.score, 1)
        self.assertEqual(MockTestAnswer.objects.filter(result=result).count(), 2)
        unanswered = MockTestAnswer.objects.get(
            result=result,
            question=second_question,
        )
        self.assertEqual(unanswered.selected_option, '')
        self.assertFalse(unanswered.is_correct)

    def test_reply_creates_notification_for_discussion_owner(self):
        owner = User.objects.create_user(username='owner', password='pass12345')
        replier = User.objects.create_user(username='replier', password='pass12345')
        discussion = Discussion.objects.create(
            subject=self.subject,
            user=owner,
            title='Need help',
            body='Can someone explain this?',
        )
        self.client.force_authenticate(user=replier)

        response = self.client.post(
            f'/api/discussions/{discussion.id}/replies/',
            {'body': 'Here is an explanation.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get(user=owner)
        self.assertEqual(notification.type, Notification.TYPE_REPLY)
        self.assertIn('replier', notification.message)
        self.assertIn(self.subject.slug, notification.link_path)
