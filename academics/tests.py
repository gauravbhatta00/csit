from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Notification
from .models import (
    Discussion,
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

    def test_question_answers_are_hidden_for_free_users(self):
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
        self.assertEqual(
            response.data[0]['answer_text'],
            'Upgrade to premium to see the answer.',
        )

    def test_question_answers_are_visible_for_premium_users(self):
        user = User.objects.create_user(username='premium', password='pass12345')
        user.is_premium = True
        user.save(update_fields=['is_premium'])
        self.client.force_authenticate(user=user)
        Question.objects.create(
            year=self.year,
            question_text='Define median.',
            answer_text='Median is the middle value.',
            marks='2',
        )

        response = self.client.get(
            f'/api/subjects/{self.subject.slug}/questions/{self.year.year}/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['answer_text'], 'Median is the middle value.')

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
