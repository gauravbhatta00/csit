import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from academics.models import AnswerContribution, Note, Question, Semester, Subject, Syllabus, SyllabusSection, SyllabusUnit, Year
from .models import ContactMessage, EmailSubscription, Testimonial

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

    def test_suspended_user_login_returns_remaining_days_message(self):
        self.user.set_account_status(
            User.STATUS_SUSPENDED,
            suspended_until=timezone.now() + timezone.timedelta(days=3),
        )
        self.user.save(update_fields=['account_status', 'is_active', 'active_token', 'suspended_until'])

        response = self.client.post(
            '/api/accounts/jwt/create/',
            {'username': 'student', 'password': 'pass12345'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('suspended for 3 more days', str(response.data['detail']))
        self.assertIn('contact support', str(response.data['detail']))

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

    def test_admin_user_patch_does_not_allow_staff_promotion(self):
        staff = User.objects.create_user(
            username='staff-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        response = self.client.patch(
            f'/api/accounts/admin/users/{self.user.id}/',
            {'is_staff': True},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_admin_can_suspend_block_and_activate_user(self):
        staff = User.objects.create_user(
            username='access-admin',
            password='pass12345',
            is_staff=True,
        )
        self.user.active_token = 'old-token'
        self.user.save(update_fields=['active_token'])
        self.client.force_authenticate(user=staff)

        suspend_response = self.client.patch(
            f'/api/accounts/admin/users/{self.user.id}/',
            {'action': 'suspend'},
            format='json',
        )
        self.user.refresh_from_db()
        self.assertEqual(suspend_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.account_status, User.STATUS_SUSPENDED)
        self.assertFalse(self.user.is_active)
        self.assertIsNone(self.user.active_token)

        block_response = self.client.patch(
            f'/api/accounts/admin/users/{self.user.id}/',
            {'action': 'block'},
            format='json',
        )
        self.user.refresh_from_db()
        self.assertEqual(block_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.account_status, User.STATUS_BLOCKED)
        self.assertFalse(self.user.is_active)

        activate_response = self.client.patch(
            f'/api/accounts/admin/users/{self.user.id}/',
            {'action': 'activate'},
            format='json',
        )
        self.user.refresh_from_db()
        self.assertEqual(activate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.account_status, User.STATUS_ACTIVE)
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.suspended_until)

    def test_admin_can_suspend_user_for_number_of_days(self):
        staff = User.objects.create_user(
            username='timed-access-admin',
            password='pass12345',
            is_staff=True,
        )
        before_request = timezone.now()
        self.client.force_authenticate(user=staff)

        response = self.client.patch(
            f'/api/accounts/admin/users/{self.user.id}/',
            {
                'action': 'suspend',
                'suspend_days': 3,
            },
            format='json',
        )

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.account_status, User.STATUS_SUSPENDED)
        self.assertFalse(self.user.is_active)
        self.assertIsNotNone(self.user.suspended_until)
        self.assertGreaterEqual(
            self.user.suspended_until,
            before_request + timezone.timedelta(days=3, seconds=-5),
        )
        self.assertIsNotNone(response.data['suspended_until'])

    def test_admin_rejects_invalid_suspend_days(self):
        staff = User.objects.create_user(
            username='invalid-days-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        response = self.client.patch(
            f'/api/accounts/admin/users/{self.user.id}/',
            {
                'action': 'suspend',
                'suspend_days': 0,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_suspension_auto_activates_on_admin_user_list(self):
        staff = User.objects.create_user(
            username='expiry-admin',
            password='pass12345',
            is_staff=True,
        )
        self.user.account_status = User.STATUS_SUSPENDED
        self.user.is_active = False
        self.user.suspended_until = timezone.now() - timezone.timedelta(minutes=1)
        self.user.save(update_fields=['account_status', 'is_active', 'suspended_until'])
        self.client.force_authenticate(user=staff)

        response = self.client.get('/api/accounts/admin/users/')

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.account_status, User.STATUS_ACTIVE)
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.suspended_until)

    def test_admin_can_delete_user(self):
        staff = User.objects.create_user(
            username='delete-admin',
            password='pass12345',
            is_staff=True,
        )
        target = User.objects.create_user(username='delete-me', password='pass12345')
        self.client.force_authenticate(user=staff)

        response = self.client.delete(f'/api/accounts/admin/users/{target.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=target.id).exists())

    def test_admin_cannot_suspend_or_delete_self(self):
        staff = User.objects.create_user(
            username='self-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        suspend_response = self.client.patch(
            f'/api/accounts/admin/users/{staff.id}/',
            {'action': 'suspend'},
            format='json',
        )
        delete_response = self.client.delete(f'/api/accounts/admin/users/{staff.id}/')

        self.assertEqual(suspend_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(delete_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.filter(id=staff.id).exists())

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

    def test_staff_user_can_upload_subject_syllabus_pdf(self):
        staff = User.objects.create_user(
            username='syllabus-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        semester = Semester.objects.create(name='Semester 1')
        subject = Subject.objects.create(semester=semester, name='Physics')
        pdf_file = SimpleUploadedFile(
            'physics-syllabus.pdf',
            b'%PDF-1.4\n%test\n',
            content_type='application/pdf',
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.patch(
                    f'/api/accounts/admin/subjects/{subject.id}/syllabus/',
                    {
                        'course_title': 'Physics',
                        'pdf_file': pdf_file,
                    },
                    format='multipart',
                )

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertTrue(response.data['pdf_file'].endswith('.pdf'))
                self.assertTrue(
                    Syllabus.objects.get(subject=subject).pdf_file.name.startswith('syllabus/')
                )

    def test_staff_user_can_import_subject_syllabus_csv(self):
        staff = User.objects.create_user(
            username='syllabus-csv-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        semester = Semester.objects.create(name='Semester 1')
        subject = Subject.objects.create(semester=semester, name='C Programming')
        csv_file = SimpleUploadedFile(
            'c_programming.csv',
            (
                'semester,course_code,course_title,credit_hrs,full_marks,pass_marks,nature,section,unit_no,unit_title,hours,content\n'
                'I,CSC115,C Programming,3,60 + 20 + 20,24 + 8 + 8,Theory + Lab,Course Description,,,,Structured C programming.\n'
                'I,CSC115,C Programming,3,60 + 20 + 20,24 + 8 + 8,Theory + Lab,Course Contents,1,Problem Solving,2 Hrs.,Algorithms and flowcharts.\n'
                'I,CSC115,C Programming,3,60 + 20 + 20,24 + 8 + 8,Theory + Lab,Recommended Books,,,,Extra book.\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            f'/api/accounts/admin/subjects/{subject.id}/syllabus/import-csv/',
            {'file': csv_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['imported_units'], 1)
        syllabus = Syllabus.objects.get(subject=subject)
        self.assertEqual(syllabus.course_no, 'CSC115')
        self.assertEqual(syllabus.units.get().title, 'Problem Solving')
        self.assertEqual(SyllabusSection.objects.get(syllabus=syllabus).title, 'Recommended Books')

    def test_staff_user_can_import_subject_notes_csv(self):
        staff = User.objects.create_user(
            username='notes-csv-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        semester = Semester.objects.create(name='Semester 1')
        subject = Subject.objects.create(semester=semester, name='C Programming')
        syllabus = Syllabus.objects.create(subject=subject, course_title='C Programming', course_no='CSC115')
        unit = SyllabusUnit.objects.create(
            syllabus=syllabus,
            title='Problem Solving',
            slug='problem-solving',
            order=1,
        )
        csv_file = SimpleUploadedFile(
            'notes.csv',
            (
                'course_code,course_title,unit_no,title,body,order,is_published\n'
                'CSC115,C Programming,1,Algorithm notes,Steps for problem solving.,1,true\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            f'/api/accounts/admin/subjects/{subject.id}/notes/import-csv/',
            {'file': csv_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['imported_count'], 1)
        note = Note.objects.get(subject=subject)
        self.assertEqual(note.unit, unit)
        self.assertEqual(note.title, 'Algorithm notes')

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

    def test_staff_user_can_bulk_import_subjects_from_csv(self):
        staff = User.objects.create_user(
            username='subject-bulk-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        semester = Semester.objects.create(name='Semester 4')
        csv_file = SimpleUploadedFile(
            'subjects.csv',
            (
                'name,slug\n'
                'Database Management System,dbms\n'
                'Theory of Computation,toc\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/accounts/admin/subjects/bulk-import/',
            {
                'file': csv_file,
                'semester_id': semester.id,
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['imported_count'], 2)
        self.assertEqual(response.data['errors'], [])
        self.assertEqual(
            Subject.objects.filter(semester=semester).count(),
            2,
        )

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

    def test_staff_user_can_bulk_import_answer_export_csv_idempotently(self):
        staff = User.objects.create_user(
            username='answer-export-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        csv_content = (
            'question_id,semester,subject,year,group,question,answer\n'
            '34605,Semester 1,Introduction to Information Technology,2081,Section A,'
            '"Compare primary memory with secondary memory.",'
            '"**Comparison:**\n\n| Primary | Secondary |\n| --- | --- |"\n'
        ).encode('utf-8')

        first_file = SimpleUploadedFile(
            'year_2081_answers.csv',
            csv_content,
            content_type='text/csv',
        )
        first_response = self.client.post(
            '/api/accounts/admin/questions/bulk-import/',
            {'file': first_file},
            format='multipart',
        )
        second_file = SimpleUploadedFile(
            'year_2081_answers.csv',
            csv_content,
            content_type='text/csv',
        )
        second_response = self.client.post(
            '/api/accounts/admin/questions/bulk-import/',
            {'file': second_file},
            format='multipart',
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data['imported_count'], 1)
        self.assertEqual(second_response.data['imported_count'], 1)
        self.assertEqual(Question.objects.filter(source_question_id='34605').count(), 1)

        question = Question.objects.get(source_question_id='34605')
        self.assertEqual(question.section.title, 'Section A')
        self.assertIn('| Primary | Secondary |', question.answer_text)
        self.assertEqual(question.year.year, '2081')
        self.assertEqual(question.year.subject.semester.name, 'Semester 1')

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

    def test_user_can_only_have_one_testimonial_and_can_edit_it(self):
        self.client.force_authenticate(user=self.user)

        create_response = self.client.post(
            '/api/accounts/testimonials/',
            {
                'role': 'Third semester student',
                'rating': 4,
                'review': 'This helped me find past questions quickly.',
            },
            format='json',
        )
        update_response = self.client.post(
            '/api/accounts/testimonials/',
            {
                'role': 'Fourth semester student',
                'rating': 5,
                'review': 'Updated review after using the mock tests too.',
            },
            format='json',
        )
        mine_response = self.client.get('/api/accounts/testimonials/?mine=1')

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(update_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Testimonial.objects.filter(user=self.user).count(), 1)
        testimonial = Testimonial.objects.get(user=self.user)
        self.assertEqual(testimonial.role, 'Fourth semester student')
        self.assertEqual(testimonial.rating, 5)
        self.assertEqual(testimonial.status, Testimonial.STATUS_PENDING)
        self.assertEqual(mine_response.data['id'], testimonial.id)

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
    @patch('accounts.services.id_token.verify_oauth2_token')
    def test_google_login_creates_user_and_returns_tokens(self, mocked_verify):
        mocked_verify.return_value = {
            'email': 'GoogleUser@example.com',
            'email_verified': True,
            'name': 'Google User',
            'picture': 'https://example.com/avatar.jpg',
        }

        response = self.client.post(
            '/api/auth/google/',
            {'credential': 'valid-google-token'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], 'googleuser@example.com')
        self.assertEqual(response.data['user']['name'], 'Google User')
        self.assertTrue(response.data['user']['is_new_user'])
        self.assertTrue(User.objects.filter(email='googleuser@example.com').exists())

    @override_settings(GOOGLE_CLIENT_ID='google-client-id')
    @patch('accounts.services.id_token.verify_oauth2_token')
    def test_google_login_rejects_invalid_token(self, mocked_verify):
        mocked_verify.side_effect = ValueError('Token has wrong audience.')

        response = self.client.post(
            '/api/auth/google/',
            {'credential': 'invalid-google-token'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
