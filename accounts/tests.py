from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from academics.models import AnswerContribution, Question, Semester, Subject, Year
from .models import ContactMessage, EmailSubscription, Notification

User = get_user_model()


class AuthApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student',
            email='student@example.com',
            password='pass12345',
        )

    def test_login_stores_active_access_token_jti(self):
        response = self.client.post(
            '/api/accounts/jwt/create/',
            {'username': 'student', 'password': 'pass12345'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        self.user.refresh_from_db()
        access = AccessToken(response.data['access'])
        self.assertEqual(self.user.active_token, access['jti'])

    def test_refresh_rotates_active_access_token_jti(self):
        login_response = self.client.post(
            '/api/accounts/jwt/create/',
            {'username': 'student', 'password': 'pass12345'},
            format='json',
        )
        self.user.refresh_from_db()
        original_jti = self.user.active_token

        refresh_response = self.client.post(
            '/api/accounts/jwt/refresh/',
            {'refresh': login_response.data['refresh']},
            format='json',
        )

        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        refreshed_access = AccessToken(refresh_response.data['access'])
        self.assertEqual(self.user.active_token, refreshed_access['jti'])
        self.assertNotEqual(self.user.active_token, original_jti)

    def test_profile_requires_authentication(self):
        response = self.client.get('/api/accounts/profile/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_dashboard_requires_staff_user(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get('/api/accounts/admin/dashboard/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_dashboard_returns_totals_for_staff_user(self):
        staff = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        response = self.client.get('/api/accounts/admin/dashboard/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('totals', response.data)
        self.assertIn('timeline', response.data)
        self.assertEqual(response.data['totals']['users'], 2)

    def test_admin_notification_only_targets_students_in_selected_semester(self):
        staff = User.objects.create_user(
            username='staff', password='pass12345', is_staff=True,
            semester='First Semester',
        )
        matching_student = User.objects.create_user(
            username='first-semester-student', password='pass12345',
            semester='first semester',
        )
        other_student = User.objects.create_user(
            username='second-semester-student', password='pass12345',
            semester='Second Semester',
        )
        inactive_student = User.objects.create_user(
            username='inactive-student', password='pass12345',
            semester='First Semester', is_active=False,
        )
        semester = Semester.objects.create(name='First Semester')
        self.client.force_authenticate(user=staff)

        response = self.client.post(
            '/api/accounts/admin/notifications/',
            {
                'recipient': 'all',
                'semester_id': semester.id,
                'message': 'Your semester timetable is available.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['sent_count'], 1)
        self.assertTrue(Notification.objects.filter(user=matching_student).exists())
        self.assertFalse(Notification.objects.filter(user=other_student).exists())
        self.assertFalse(Notification.objects.filter(user=inactive_student).exists())
        self.assertFalse(Notification.objects.filter(user=staff).exists())

    def test_admin_semester_and_subject_lists_require_staff_user(self):
        self.client.force_authenticate(user=self.user)

        semester_response = self.client.get('/api/accounts/admin/semesters/')
        subject_response = self.client.get('/api/accounts/admin/subjects/')

        self.assertEqual(semester_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(subject_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_user_can_create_content_from_admin_endpoints(self):
        staff = User.objects.create_user(
            username='content-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        semester_response = self.client.post(
            '/api/accounts/admin/semesters/',
            {'name': 'Semester 8'},
            format='json',
        )
        self.assertEqual(semester_response.status_code, status.HTTP_201_CREATED)

        subject_response = self.client.post(
            '/api/accounts/admin/subjects/',
            {
                'name': 'Artificial Intelligence',
                'semester_id': semester_response.data['id'],
            },
            format='json',
        )
        self.assertEqual(subject_response.status_code, status.HTTP_201_CREATED)

        question_response = self.client.post(
            '/api/accounts/admin/questions/',
            {
                'subject_id': subject_response.data['id'],
                'year': '2081',
                'question_text': 'Define intelligent agent.',
                'answer_text': 'An intelligent agent perceives and acts.',
                'marks': '5',
            },
            format='json',
        )
        self.assertEqual(question_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(question_response.data['subject'], 'Artificial Intelligence')
        self.assertEqual(question_response.data['year'], '2081')

    def test_staff_user_can_bulk_import_questions_from_csv(self):
        staff = User.objects.create_user(
            username='bulk-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        semester_response = self.client.post(
            '/api/accounts/admin/semesters/',
            {'name': 'Semester 5'},
            format='json',
        )
        subject_response = self.client.post(
            '/api/accounts/admin/subjects/',
            {
                'name': 'Computer Graphics',
                'semester_id': semester_response.data['id'],
            },
            format='json',
        )
        csv_file = SimpleUploadedFile(
            'questions.csv',
            (
                'question_text,answer_text,marks\n'
                '"What is rasterization?","Rasterization converts vector geometry into pixels.",5\n'
                '"Define clipping.","Clipping removes objects outside the view volume.",4\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/accounts/admin/questions/bulk-import/',
            {
                'file': csv_file,
                'subject_id': subject_response.data['id'],
                'year': '2081',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['imported_count'], 2)
        self.assertEqual(response.data['errors'], [])

    def test_staff_user_can_bulk_import_main_py_question_and_answer_csvs(self):
        staff = User.objects.create_user(
            username='scraper-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        questions_csv = SimpleUploadedFile(
            '2081_questions.csv',
            (
                'question_id,semester,subject,subject_slug,year,question_number,section,question,has_answer,exam_time,instructions,source_url\n'
                '34605,Semester 3,Computer Architecture,csc208,2081,1,Group A,"Define cache memory.",Yes,3 Hours,"Answer all questions.",https://example.com\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )
        answers_csv = SimpleUploadedFile(
            '2081_answers.csv',
            (
                'question_id,answer_markdown,image_paths,answer_source_url\n'
                '34605,"Cache memory is high-speed memory.",images/34605_1.jpg,https://example.com/question/34605\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/accounts/admin/questions/bulk-import/',
            {
                'file': questions_csv,
                'answers_file': answers_csv,
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['imported_count'], 1)
        self.assertEqual(response.data['questions'][0]['subject'], 'Computer Architecture')
        self.assertIn('Cache memory', response.data['questions'][0]['answer_text'])

    def test_staff_user_can_approve_answer_contribution(self):
        staff = User.objects.create_user(
            username='review-admin',
            password='pass12345',
            is_staff=True,
        )
        student = User.objects.create_user(
            username='answer-helper',
            password='pass12345',
        )
        semester = Semester.objects.create(name='Semester 2')
        subject = Subject.objects.create(semester=semester, name='Discrete Structure')
        year = Year.objects.create(subject=subject, year='2081')
        question = Question.objects.create(
            year=year,
            question_text='Define graph.',
            answer_text='A graph has vertices and edges.',
        )
        contribution = AnswerContribution.objects.create(
            question=question,
            user=student,
            answer_text='A graph is an ordered pair of vertices and edges.',
        )
        self.client.force_authenticate(user=staff)

        response = self.client.patch(
            f'/api/accounts/admin/answer-contributions/{contribution.id}/',
            {'status': AnswerContribution.STATUS_APPROVED},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], AnswerContribution.STATUS_APPROVED)
        self.assertEqual(response.data['image'], '')
        contribution.refresh_from_db()
        self.assertEqual(contribution.reviewed_by, staff)
        self.assertIsNotNone(contribution.reviewed_at)

    def test_contact_message_can_be_submitted_without_login(self):
        response = self.client.post(
            '/api/accounts/contact/',
            {
                'name': 'Student User',
                'email': 'student@example.com',
                'message': 'Please add more resources for statistics.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ContactMessage.objects.count(), 1)
        message = ContactMessage.objects.get()
        self.assertEqual(message.name, 'Student User')
        self.assertEqual(message.email, 'student@example.com')

    def test_email_subscription_can_be_submitted_without_login(self):
        response = self.client.post(
            '/api/accounts/email-subscriptions/',
            {'email': 'STUDENT@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EmailSubscription.objects.count(), 1)
        self.assertEqual(
            EmailSubscription.objects.get().email,
            'student@example.com',
        )

    def test_duplicate_email_subscription_is_idempotent(self):
        EmailSubscription.objects.create(
            email='student@example.com',
            is_active=False,
        )

        response = self.client.post(
            '/api/accounts/email-subscriptions/',
            {'email': 'student@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(EmailSubscription.objects.count(), 1)
        self.assertTrue(EmailSubscription.objects.get().is_active)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        FRONTEND_BASE_URL='http://localhost:3000',
    )
    def test_password_reset_request_sends_email_without_login(self):
        response = self.client.post(
            '/api/accounts/password-reset/',
            {'email': 'student@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/reset-password?', mail.outbox[0].body)

    def test_password_reset_confirm_updates_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            '/api/accounts/password-reset/confirm/',
            {
                'uid': uid,
                'token': token,
                'password': 'newpass12345',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass12345'))
        self.assertIsNone(self.user.active_token)

    @override_settings(GOOGLE_CLIENT_ID='google-client-id')
    @patch('accounts.services.requests.get')
    def test_google_login_creates_user_and_returns_tokens(self, mocked_get):
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {
            'aud': 'google-client-id',
            'email': 'GoogleUser@example.com',
            'email_verified': 'true',
        }
        mocked_get.return_value = mocked_response

        response = self.client.post(
            '/api/accounts/google/',
            {'credential': 'valid-google-token'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertTrue(User.objects.filter(email='googleuser@example.com').exists())

    @override_settings(GOOGLE_CLIENT_ID='google-client-id')
    @patch('accounts.services.requests.get')
    def test_google_login_rejects_invalid_audience(self, mocked_get):
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {
            'aud': 'other-client-id',
            'email': 'student@example.com',
            'email_verified': 'true',
        }
        mocked_get.return_value = mocked_response

        response = self.client.post(
            '/api/accounts/google/',
            {'credential': 'invalid-google-token'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
