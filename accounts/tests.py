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

from academics.models import AnswerContribution, CreditPerson, MockTest, Note, Question, Semester, Subject, Syllabus, SyllabusSection, SyllabusUnit, Year
from .models import (
    ContactMessage,
    ContributionSubmission,
    EmailSubscription,
    Notification,
    Testimonial,
)

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

    def test_staff_user_can_send_custom_notification_to_specific_user(self):
        staff = User.objects.create_user(
            username='notification-admin',
            password='pass12345',
            is_staff=True,
        )
        target = User.objects.create_user(
            username='notification-target',
            password='pass12345',
        )
        self.client.force_authenticate(user=staff)

        response = self.client.post(
            '/api/accounts/admin/notifications/',
            {
                'recipient': 'user',
                'user_id': target.id,
                'message': 'Mock test starts tomorrow.',
                'link_path': '/mock-tests',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['sent_count'], 1)
        notification = Notification.objects.get(user=target)
        self.assertEqual(notification.type, Notification.TYPE_CUSTOM)
        self.assertEqual(notification.message, 'Mock test starts tomorrow.')
        self.assertEqual(notification.link_path, '/mock-tests')
        self.assertEqual(response.data['notifications'][0]['username'], target.username)

    def test_staff_user_can_send_custom_notification_to_all_active_users(self):
        staff = User.objects.create_user(
            username='broadcast-admin',
            password='pass12345',
            is_staff=True,
        )
        active_user = User.objects.create_user(
            username='active-recipient',
            password='pass12345',
        )
        inactive_user = User.objects.create_user(
            username='inactive-recipient',
            password='pass12345',
            is_active=False,
        )
        self.client.force_authenticate(user=staff)

        response = self.client.post(
            '/api/accounts/admin/notifications/',
            {
                'recipient': 'all',
                'message': 'New syllabus notes are available.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['sent_count'], 3)
        self.assertEqual(
            set(Notification.objects.values_list('user__username', flat=True)),
            {'student', 'broadcast-admin', 'active-recipient'},
        )
        self.assertFalse(Notification.objects.filter(user=inactive_user).exists())
        self.assertTrue(Notification.objects.filter(user=active_user).exists())

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

    def test_staff_user_can_import_syllabus_csv_with_long_unit_slug(self):
        staff = User.objects.create_user(
            username='syllabus-long-slug-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        semester = Semester.objects.create(name='Semester 2')
        subject = Subject.objects.create(semester=semester, name='Object Oriented Programming')
        csv_file = SimpleUploadedFile(
            'object_oriented_programming.csv',
            (
                'semester,course_code,course_title,credit_hrs,full_marks,pass_marks,nature,section,unit_no,unit_title,hours,content\n'
                'II,CSC166,Object Oriented Programming,3,60 + 20 + 20,24 + 8 + 8,,Course Contents,6,"Virtual Function, Polymorphism, and miscellaneous C++ Features",5 Hrs.,Polymorphism and virtual functions.\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            f'/api/accounts/admin/subjects/{subject.id}/syllabus/import-csv/',
            {'file': csv_file},
            format='multipart',
            HTTP_X_FORWARDED_PROTO='https',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        unit = SyllabusUnit.objects.get(syllabus__subject=subject)
        self.assertLessEqual(
            len(unit.slug),
            SyllabusUnit._meta.get_field('slug').max_length,
        )

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
                'course_code,course_title,unit_no,title,body,credit_name,credit_designation,order,is_published\n'
                'CSC115,C Programming,1,Algorithm notes,Steps for problem solving.,Jane Doe,CSIT Lecturer,1,true\n'
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
        self.assertEqual(note.credit_name, 'Jane Doe')
        self.assertEqual(note.credit_designation, 'CSIT Lecturer')

    def test_staff_user_can_create_credit_person(self):
        staff = User.objects.create_user(
            username='credit-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        response = self.client.post(
            '/api/accounts/admin/credit-people/',
            {
                'name': 'Jane Contributor',
                'designation': 'Lecturer',
                'link_url': 'https://example.com/profile',
                'portfolio_url': 'https://example.com/portfolio',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Jane Contributor')
        self.assertEqual(response.data['designation'], 'Lecturer')
        self.assertTrue(CreditPerson.objects.filter(name='Jane Contributor').exists())

    def test_staff_user_can_list_credit_people(self):
        staff = User.objects.create_user(
            username='credit-list-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        CreditPerson.objects.create(name='Jane Contributor', designation='Lecturer')

        response = self.client.get('/api/accounts/admin/credit-people/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['name'], 'Jane Contributor')
        self.assertEqual(response.data[0]['designation'], 'Lecturer')

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

    def test_staff_user_can_import_mock_test_from_oop_style_csv(self):
        staff = User.objects.create_user(
            username='mock-csv-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        semester = Semester.objects.create(name='Semester II')
        subject = Subject.objects.create(
            semester=semester,
            name='Object Oriented Programming',
            slug='object-oriented-programming',
        )
        csv_file = SimpleUploadedFile(
            'oop.csv',
            (
                '"Semester","Subject","Unit","Question","Option A","Option B","Option C","Option D","Correct Answer","Difficulty"\n'
                '"II","Object Oriented Programming","Unit 1","What is encapsulation?","Inheritance","Data hiding","Macro","Loop","B","Hard"\n'
                '"II","Object Oriented Programming","Unit 1","Which concept supports reuse?","Inheritance","Compilation","Token","Array","A","Hard"\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/accounts/admin/mock-tests/import-csv/',
            {
                'file': csv_file,
                'subject_id': subject.id,
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['imported_count'], 2)
        self.assertEqual(response.data['errors'], [])
        mock_test = MockTest.objects.get(subject=subject)
        self.assertEqual(mock_test.title, 'Object Oriented Programming Mock Test')
        self.assertEqual(mock_test.duration_minutes, 3)
        self.assertEqual(mock_test.total_marks, 2)
        self.assertEqual(mock_test.questions.count(), 2)

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

    def test_staff_user_can_bulk_import_csv_metadata_without_defaults(self):
        staff = User.objects.create_user(
            username='csv-only-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        csv_file = SimpleUploadedFile(
            'questions_with_metadata.csv',
            (
                'Question ID,Semester,Subject,Year,Group,Question,Answer\n'
                '44601,Semester 4,Database Management System,2080,Group B,'
                '"What is normalization?","Normalization reduces redundancy."\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/accounts/admin/questions/bulk-import/',
            {'file': csv_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['imported_count'], 1)
        self.assertEqual(response.data['errors'], [])

        question = Question.objects.get(source_question_id='44601')
        self.assertEqual(question.section.title, 'Group B')
        self.assertEqual(question.year.year, '2080')
        self.assertEqual(question.year.subject.name, 'Database Management System')
        self.assertEqual(question.year.subject.semester.name, 'Semester 4')
        self.assertEqual(question.answer_text, 'Normalization reduces redundancy.')

    def test_staff_user_can_upload_answer_only_csv_for_existing_imported_question(self):
        staff = User.objects.create_user(
            username='answer-only-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)
        semester = Semester.objects.create(name='Semester 1')
        subject = Subject.objects.create(
            semester=semester,
            name='Introduction to Information Technology',
        )
        year = Year.objects.create(subject=subject, year='2081')
        question = Question.objects.create(
            year=year,
            source_question_id='34605',
            question_text='Compare primary memory with secondary memory.',
            answer_text='Old answer.',
            marks='5',
            order=2,
        )
        csv_file = SimpleUploadedFile(
            'year_2081_answers.csv',
            (
                'question_id,answer_markdown,image_paths,answer_source_url\n'
                '34605,"Updated **markdown** answer.",images/34605_1.jpg,'
                'https://example.com/question/34605\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/accounts/admin/questions/bulk-import/',
            {'file': csv_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['imported_count'], 1)
        self.assertEqual(response.data['errors'], [])

        question.refresh_from_db()
        self.assertEqual(question.id, Question.objects.get(source_question_id='34605').id)
        self.assertEqual(question.question_text, 'Compare primary memory with secondary memory.')
        self.assertEqual(question.answer_text, 'Updated **markdown** answer.')
        self.assertEqual(question.answer_image_paths, 'images/34605_1.jpg')
        self.assertEqual(question.answer_source_url, 'https://example.com/question/34605')
        self.assertEqual(question.marks, '5')
        self.assertEqual(question.order, 2)

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
        other_student = User.objects.create_user(
            username='other-answer-helper',
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
        notification = Notification.objects.get(user=student)
        self.assertEqual(notification.type, Notification.TYPE_CONTRIBUTION)
        self.assertIn('accepted', notification.message)
        self.assertEqual(
            notification.link_path,
            f'/semester/{semester.slug}/subject/{subject.slug}',
        )
        self.assertFalse(Notification.objects.filter(user=other_student).exists())

    def test_staff_user_can_promote_answer_contribution_to_main_answer(self):
        staff = User.objects.create_user(
            username='main-answer-admin',
            password='pass12345',
            is_staff=True,
        )
        student = User.objects.create_user(
            username='main-answer-helper',
            password='pass12345',
        )
        semester = Semester.objects.create(name='Semester 2')
        subject = Subject.objects.create(semester=semester, name='Discrete Structure')
        year = Year.objects.create(subject=subject, year='2081')
        question = Question.objects.create(
            year=year,
            question_text='Define graph.',
            answer_text='Old main answer.',
        )
        previous_main = AnswerContribution.objects.create(
            question=question,
            user=student,
            answer_text='Previous main answer.',
            status=AnswerContribution.STATUS_APPROVED,
            is_main_answer=True,
        )
        contribution = AnswerContribution.objects.create(
            question=question,
            user=student,
            answer_text='Promoted main answer.',
        )
        self.client.force_authenticate(user=staff)

        response = self.client.patch(
            f'/api/accounts/admin/answer-contributions/{contribution.id}/',
            {'use_as_main_answer': True},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], AnswerContribution.STATUS_APPROVED)
        self.assertTrue(response.data['is_main_answer'])
        question.refresh_from_db()
        contribution.refresh_from_db()
        previous_main.refresh_from_db()
        self.assertEqual(question.answer_text, 'Promoted main answer.')
        self.assertTrue(contribution.is_main_answer)
        self.assertFalse(previous_main.is_main_answer)

    def test_staff_user_rejects_answer_contribution_with_reason_notification(self):
        staff = User.objects.create_user(
            username='reject-contribution-admin',
            password='pass12345',
            is_staff=True,
        )
        student = User.objects.create_user(
            username='rejected-answer-helper',
            password='pass12345',
        )
        other_student = User.objects.create_user(
            username='not-the-contributor',
            password='pass12345',
        )
        semester = Semester.objects.create(name='Semester 2')
        subject = Subject.objects.create(semester=semester, name='Discrete Structure')
        year = Year.objects.create(subject=subject, year='2081')
        question = Question.objects.create(
            year=year,
            question_text='Define relation.',
            answer_text='A relation is a subset of a Cartesian product.',
        )
        contribution = AnswerContribution.objects.create(
            question=question,
            user=student,
            answer_text='Relation means related things.',
        )
        self.client.force_authenticate(user=staff)

        missing_reason_response = self.client.patch(
            f'/api/accounts/admin/answer-contributions/{contribution.id}/',
            {'status': AnswerContribution.STATUS_REJECTED},
            format='json',
        )

        self.assertEqual(missing_reason_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Notification.objects.count(), 0)

        response = self.client.patch(
            f'/api/accounts/admin/answer-contributions/{contribution.id}/',
            {
                'status': AnswerContribution.STATUS_REJECTED,
                'rejection_reason': 'Please provide a clearer explanation.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], AnswerContribution.STATUS_REJECTED)
        self.assertEqual(
            response.data['rejection_reason'],
            'Please provide a clearer explanation.',
        )
        contribution.refresh_from_db()
        self.assertEqual(contribution.reviewed_by, staff)
        self.assertIsNotNone(contribution.reviewed_at)
        self.assertEqual(
            contribution.rejection_reason,
            'Please provide a clearer explanation.',
        )
        notification = Notification.objects.get(user=student)
        self.assertEqual(notification.type, Notification.TYPE_CONTRIBUTION)
        self.assertIn('rejected', notification.message)
        self.assertIn('Please provide a clearer explanation.', notification.message)
        self.assertEqual(
            notification.link_path,
            f'/semester/{semester.slug}/subject/{subject.slug}',
        )
        self.assertFalse(Notification.objects.filter(user=other_student).exists())

    def test_staff_user_can_edit_answer_contribution_before_approval(self):
        staff = User.objects.create_user(
            username='edit-contribution-admin',
            password='pass12345',
            is_staff=True,
        )
        student = User.objects.create_user(
            username='caption-helper',
            password='pass12345',
        )
        semester = Semester.objects.create(name='Semester 2')
        subject = Subject.objects.create(semester=semester, name='Discrete Structure')
        year = Year.objects.create(subject=subject, year='2081')
        question = Question.objects.create(
            year=year,
            question_text='Define tree.',
            answer_text='A tree is a connected acyclic graph.',
        )
        contribution = AnswerContribution.objects.create(
            question=question,
            user=student,
            answer_text='Random heading\nA tree is connected and acyclic.',
        )
        self.client.force_authenticate(user=staff)

        response = self.client.patch(
            f'/api/accounts/admin/answer-contributions/{contribution.id}/',
            {
                'answer_text': 'A tree is connected and acyclic.',
                'status': AnswerContribution.STATUS_APPROVED,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['answer_text'], 'A tree is connected and acyclic.')
        self.assertEqual(response.data['status'], AnswerContribution.STATUS_APPROVED)
        contribution.refresh_from_db()
        self.assertEqual(contribution.answer_text, 'A tree is connected and acyclic.')
        self.assertEqual(contribution.reviewed_by, staff)

    def test_staff_user_can_replace_or_remove_answer_contribution_image(self):
        staff = User.objects.create_user(
            username='image-contribution-admin',
            password='pass12345',
            is_staff=True,
        )
        student = User.objects.create_user(
            username='image-helper',
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
            answer_text='',
        )
        image_file = SimpleUploadedFile(
            'answer.gif',
            (
                b'GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00'
                b'\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00'
                b'\x00\x02\x02D\x01\x00;'
            ),
            content_type='image/gif',
        )
        self.client.force_authenticate(user=staff)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                image_response = self.client.patch(
                    f'/api/accounts/admin/answer-contributions/{contribution.id}/',
                    {
                        'answer_text': '',
                        'image': image_file,
                    },
                    format='multipart',
                )
                self.assertEqual(image_response.status_code, status.HTTP_200_OK)
                self.assertTrue(image_response.data['image'])

                remove_response = self.client.patch(
                    f'/api/accounts/admin/answer-contributions/{contribution.id}/',
                    {
                        'answer_text': 'Text-only corrected answer.',
                        'remove_image': 'true',
                    },
                    format='multipart',
                )

        self.assertEqual(remove_response.status_code, status.HTTP_200_OK)
        self.assertEqual(remove_response.data['image'], '')
        self.assertEqual(remove_response.data['answer_text'], 'Text-only corrected answer.')
        contribution.refresh_from_db()
        self.assertFalse(contribution.image)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        CONTACT_EMAIL_FROM='hi@ramrocsit.com',
        CONTACT_EMAIL_RECIPIENT='hi@ramrocsit.com',
    )
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
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['hi@ramrocsit.com'])
        self.assertEqual(mail.outbox[0].from_email, 'hi@ramrocsit.com')
        self.assertIn('Please add more resources', mail.outbox[0].body)

    def test_contribution_submission_can_be_reviewed_by_admin(self):
        response = self.client.post(
            '/api/accounts/contributions/',
            {
                'name': 'Student User',
                'email': 'Student@Example.com',
                'contribution_type': 'Chapter notes',
                'semester': 'Semester 3',
                'subject': 'Data Structure and Algorithm',
                'resource_link': 'https://example.com/notes',
                'details': 'I can share stack and queue notes.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ContributionSubmission.objects.count(), 1)
        submission = ContributionSubmission.objects.get()
        self.assertEqual(submission.email, 'student@example.com')
        self.assertEqual(submission.status, ContributionSubmission.STATUS_PENDING)

        staff = User.objects.create_user(
            username='contribution-review-admin',
            password='pass12345',
            is_staff=True,
        )
        self.client.force_authenticate(user=staff)

        list_response = self.client.get(
            '/api/accounts/admin/contributions/?status=pending',
        )
        update_response = self.client.patch(
            f'/api/accounts/admin/contributions/{submission.id}/',
            {'status': ContributionSubmission.STATUS_APPROVED},
            format='json',
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        submission.refresh_from_db()
        self.assertEqual(submission.status, ContributionSubmission.STATUS_APPROVED)
        self.assertEqual(submission.reviewed_by, staff)

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
        self.assertIn('http://localhost:3000/reset-password?', mail.outbox[0].body)

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
