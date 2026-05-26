import csv
import io
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from PIL import Image, UnidentifiedImageError
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.shortcuts import get_object_or_404
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.text import slugify
from academics.models import (
    Discussion,
    DiscussionReply,
    AnswerContribution,
    MockTest,
    MockTestQuestion,
    MockTestResult,
    Note,
    Question,
    QuestionPaper,
    QuestionSection,
    Semester,
    Subject,
    Syllabus,
    SyllabusSection,
    SyllabusUnit,
    Year,
)
from .models import (
    ContactMessage,
    EmailSubscription,
    Notification,
    Testimonial,
)
from .serializers import (
    ContactMessageSerializer,
    EmailSubscriptionSerializer,
    GoogleLoginSerializer,
    NotificationSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
    TestimonialSerializer,
)
from .services import (
    GoogleAuthConfigurationError,
    build_login_response,
    build_unique_username,
)


logger = logging.getLogger(__name__)


SYLLABUS_FIELD_SECTIONS = {
    'course description': 'course_description',
    'course objective': 'course_objective',
    'course objectives': 'course_objective',
    'laboratory works': 'laboratory_work',
    'laboratory work': 'laboratory_work',
    'text books': 'text_books',
    'text book': 'text_books',
    'reference books': 'reference_books',
    'reference book': 'reference_books',
}


def clean_csv_value(value):
    return (value or '').strip()


def compact_match_value(value):
    return ''.join(character for character in clean_csv_value(value).lower() if character.isalnum())


def normalize_course_match(value):
    normalized = compact_match_value(value)
    replacements = {
        'structures': 'structure',
        'systems': 'system',
        'algorithms': 'algorithm',
        'administration': 'administrator',
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def append_csv_text(current, value):
    value = clean_csv_value(value)
    if not value:
        return current
    current = clean_csv_value(current)
    return f'{current}\n{value}' if current else value


def parse_csv_order(value):
    try:
        return int(float(clean_csv_value(value)))
    except (TypeError, ValueError):
        return 0


def parse_csv_bool(value, default=True):
    if isinstance(value, bool):
        return value
    normalized = clean_csv_value(value).lower()
    if not normalized:
        return default
    return normalized in {'1', 'true', 'yes', 'y', 'published'}


def get_csv_row_value(row, *keys):
    normalized_row = {
        compact_match_value(key): value
        for key, value in row.items()
    }
    for key in keys:
        value = normalized_row.get(compact_match_value(key))
        if clean_csv_value(value):
            return clean_csv_value(value)
    return ''


def read_uploaded_csv(uploaded_file):
    try:
        text = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        text = uploaded_file.read().decode('cp1252')
    return list(csv.DictReader(io.StringIO(text)))


def validate_pdf_upload(uploaded_file):
    if not uploaded_file:
        return None
    if not uploaded_file.name.lower().endswith('.pdf'):
        return 'Only PDF files are allowed.'
    content_type = getattr(uploaded_file, 'content_type', '')
    if content_type and content_type not in {'application/pdf', 'application/x-pdf', 'application/octet-stream'}:
        return 'Upload a valid PDF file.'
    return None


def derive_note_title(subject, unit, pdf_file):
    if unit:
        return unit.title
    if pdf_file:
        title = pdf_file.name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').strip()
        if title:
            return title
    return f'{subject.name} Note'


def build_note_slug(subject, unit, title):
    if unit:
        return unit.slug
    return slugify(title) or f'note-{subject.notes.count() + 1}'


def choose_subject_csv_rows(subject, rows):
    grouped_rows = {}
    for row in rows:
        key = (
            clean_csv_value(row.get('course_code')),
            clean_csv_value(row.get('course_title')),
        )
        grouped_rows.setdefault(key, []).append(row)

    if not grouped_rows:
        return []

    subject_name = normalize_course_match(subject.name)
    for (course_code, course_title), grouped in grouped_rows.items():
        syllabus = getattr(subject, 'syllabus', None)
        if syllabus and course_code and compact_match_value(course_code) == compact_match_value(syllabus.course_no):
            return grouped
        if course_title and normalize_course_match(course_title) == subject_name:
            return grouped

    if len(grouped_rows) == 1:
        return next(iter(grouped_rows.values()))

    return []


def unique_syllabus_unit_slug(syllabus, title, used_slugs):
    base = slugify(title) or 'unit'
    slug = base
    index = 2
    while slug in used_slugs or SyllabusUnit.objects.filter(syllabus=syllabus, slug=slug).exists():
        slug = f'{base}-{index}'
        index += 1
    used_slugs.add(slug)
    return slug


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token is required.'}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            request.user.active_token = None
            request.user.save()
            return Response({'message': 'Logged out successfully.'})
        except TokenError:
            return Response({'error': 'Invalid or expired token.'}, status=400)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        serializer = ProfileSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            ProfileSerializer(request.user, context={'request': request}).data
        )


class TestimonialListCreateView(APIView):
    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        if request.query_params.get('mine') in {'1', 'true', 'True'}:
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {'detail': 'Authentication is required.'},
                    status=401,
                )
            testimonial = Testimonial.objects.filter(user=request.user).first()
            if not testimonial:
                return Response(None)
            return Response(TestimonialSerializer(testimonial).data)

        try:
            limit = int(request.query_params.get('limit', 8))
        except (TypeError, ValueError):
            limit = 8

        limit = max(1, min(limit, 16))
        testimonials = (
            Testimonial.objects
            .select_related('user')
            .filter(status=Testimonial.STATUS_APPROVED)
            .order_by('-created_at')[:limit]
        )
        serializer = TestimonialSerializer(testimonials, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication is required to submit a review.'},
                status=401,
            )

        data = request.data.copy()
        data['name'] = request.user.username

        serializer = TestimonialSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        testimonial = Testimonial.objects.filter(user=request.user).first()
        if testimonial:
            testimonial.name = serializer.validated_data['name']
            testimonial.role = serializer.validated_data.get('role', '')
            testimonial.rating = serializer.validated_data['rating']
            testimonial.review = serializer.validated_data['review']
            testimonial.status = Testimonial.STATUS_PENDING
            testimonial.reviewed_by = None
            testimonial.reviewed_at = None
            testimonial.save(
                update_fields=[
                    'name',
                    'role',
                    'rating',
                    'review',
                    'status',
                    'reviewed_by',
                    'reviewed_at',
                    'updated_at',
                ]
            )
        else:
            testimonial = serializer.save(
                user=request.user,
                status=Testimonial.STATUS_PENDING,
            )
        return Response(TestimonialSerializer(testimonial).data, status=201)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = (
                f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password"
                f"?uid={uid}&token={token}"
            )
            send_mail(
                subject='Reset your Sabaiko CSIT password',
                message=(
                    "Use this link to reset your Sabaiko CSIT password:\n\n"
                    f"{reset_url}\n\n"
                    "If you did not request this, you can ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )

        return Response({
            'detail': 'If an account exists for that email, a reset link has been sent.'
        })


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        User = get_user_model()

        try:
            user_id = force_str(urlsafe_base64_decode(data['uid']))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'detail': 'Password reset link is invalid.'}, status=400)

        if not default_token_generator.check_token(user, data['token']):
            return Response({'detail': 'Password reset link is invalid or expired.'}, status=400)

        user.set_password(data['password'])
        user.active_token = None
        user.save(update_fields=['password', 'active_token'])
        return Response({'detail': 'Password has been reset.'})


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except GoogleAuthConfigurationError as exc:
            logger.error('Google login is not configured: %s', exc)
            return Response({'detail': str(exc)}, status=500)

        google_user = serializer.validated_data['google_user']
        email = google_user['email'].strip().lower()
        User = get_user_model()
        is_new_user = False

        try:
            with transaction.atomic():
                user = User.objects.filter(email__iexact=email).first()
                if not user:
                    user = self.create_google_user(User, email, google_user)
                    is_new_user = True
        except IntegrityError:
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                logger.exception('Google login user creation failed after integrity error.')
                return Response(
                    {'detail': 'User creation/login failure.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            is_new_user = False
        except Exception:
            logger.exception('Google login user creation/login failed.')
            return Response(
                {'detail': 'User creation/login failure.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            'Google login succeeded for user_id=%s is_new_user=%s',
            user.id,
            is_new_user,
        )
        return Response(build_login_response(user, google_user, is_new_user))

    def create_google_user(self, User, email, google_user):
        user_fields = {field.name for field in User._meta.get_fields()}
        create_kwargs = {'email': email}

        if 'username' in user_fields:
            create_kwargs['username'] = build_unique_username(email)
        if 'first_name' in user_fields:
            create_kwargs['first_name'] = google_user.get('given_name', '')[:150]
        if 'last_name' in user_fields:
            create_kwargs['last_name'] = google_user.get('family_name', '')[:150]

        user = User.objects.create_user(password=None, **create_kwargs)
        user.set_unusable_password()
        user.save(update_fields=['password'])
        return user


class ContactMessageCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        return Response(ContactMessageSerializer(message).data, status=201)


class EmailSubscriptionCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription, created = EmailSubscription.objects.update_or_create(
            email=serializer.validated_data['email'],
            defaults={'is_active': True},
        )
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            EmailSubscriptionSerializer(subscription).data,
            status=status_code,
        )


class NotificationListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(id=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notification not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification).data)


class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).update(is_read=True)
        return Response({'message': 'All notifications marked as read.'})


class UnreadNotificationCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()
        return Response({'unread_count': count})


class DeleteNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(id=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notification not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminDashboardView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        today = timezone.now().date()
        start_date = today - timezone.timedelta(days=29)
        mock_attempts_by_day = {
            item['day'].isoformat(): item['attempts']
            for item in MockTestResult.objects.filter(
                completed_at__date__gte=start_date,
            )
            .annotate(day=TruncDate('completed_at'))
            .values('day')
            .annotate(attempts=Count('id'))
            .order_by('day')
        }
        timeline = []

        for offset in range(30):
            day = start_date + timezone.timedelta(days=offset)
            key = day.isoformat()
            timeline.append({
                'date': key,
                'mock_attempts': mock_attempts_by_day.get(key, 0),
            })

        questions_by_semester = [
            {
                'semester': item['name'],
                'subjects': item['subject_count'],
                'questions': item['question_count'],
            }
            for item in Semester.objects.annotate(
                subject_count=Count('subjects', distinct=True),
                question_count=Count('subjects__years__questions', distinct=True),
            )
            .values('name', 'subject_count', 'question_count')
            .order_by('id')
        ]
        mock_attempts_by_subject = [
            {
                'subject': item['mock_test__subject__name'],
                'attempts': item['attempts'],
            }
            for item in MockTestResult.objects.values(
                'mock_test__subject__name',
            )
            .annotate(attempts=Count('id'))
            .order_by('-attempts')[:8]
        ]
        recent_discussions = [
            {
                'id': discussion.id,
                'title': discussion.title,
                'subject': discussion.subject.name,
                'username': discussion.user.username,
                'created_at': discussion.created_at,
                'reply_count': discussion.replies.count(),
            }
            for discussion in Discussion.objects.select_related(
                'subject',
                'user',
            ).prefetch_related('replies')[:5]
        ]
        average_score = MockTestResult.objects.aggregate(
            average=Avg('score'),
        )['average']

        return Response({
            'totals': {
                'users': request.user.__class__.objects.count(),
                'staff_users': request.user.__class__.objects.filter(
                    is_staff=True,
                ).count(),
                'semesters': Semester.objects.count(),
                'subjects': Subject.objects.count(),
                'years': Year.objects.count(),
                'questions': Question.objects.count(),
                'syllabus_files': Syllabus.objects.count(),
                'paper_files': QuestionPaper.objects.count(),
                'mock_tests': MockTest.objects.count(),
                'mock_attempts': MockTestResult.objects.count(),
                'discussions': Discussion.objects.count(),
                'discussion_replies': DiscussionReply.objects.count(),
                'notifications': Notification.objects.count(),
                'average_mock_score': round(float(average_score or 0), 2),
            },
            'timeline': timeline,
            'questions_by_semester': questions_by_semester,
            'mock_attempts_by_subject': mock_attempts_by_subject,
            'recent_discussions': recent_discussions,
        })


class AdminSemesterListView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_semester(self, semester):
        return {
            'id': semester.id,
            'name': semester.name,
            'slug': semester.slug,
            'subject_count': getattr(semester, 'subject_count', 0),
            'year_count': getattr(semester, 'year_count', 0),
            'question_count': getattr(semester, 'question_count', 0),
            'mock_test_count': getattr(semester, 'mock_test_count', 0),
        }

    def get_queryset(self):
        return Semester.objects.annotate(
            subject_count=Count('subjects', distinct=True),
            year_count=Count('subjects__years', distinct=True),
            question_count=Count('subjects__years__questions', distinct=True),
            mock_test_count=Count('subjects__mock_tests', distinct=True),
        ).order_by('id')

    def get(self, request):
        return Response([
            self.serialize_semester(semester)
            for semester in self.get_queryset()
        ])

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        slug = (request.data.get('slug') or '').strip()

        if not name:
            return Response({'detail': 'Semester name is required.'}, status=400)

        semester = Semester(name=name)
        if slug:
            semester.slug = slugify(slug)
        semester.save()
        semester = self.get_queryset().get(id=semester.id)
        return Response(self.serialize_semester(semester), status=201)


class AdminSemesterDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        semester = get_object_or_404(Semester, pk=pk)
        name = request.data.get('name')
        slug = request.data.get('slug')

        if name is not None:
            name = name.strip()
            if not name:
                return Response({'detail': 'Semester name is required.'}, status=400)
            semester.name = name

        if slug is not None:
            semester.slug = slugify(slug.strip()) if slug.strip() else ''

        semester.save()
        return Response({
            'id': semester.id,
            'name': semester.name,
            'slug': semester.slug,
        })

    def delete(self, request, pk):
        semester = get_object_or_404(Semester, pk=pk)
        semester.delete()
        return Response(status=204)


class AdminSubjectListView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_subject(self, subject):
        return {
            'id': subject.id,
            'name': subject.name,
            'slug': subject.slug,
            'semester': subject.semester.name,
            'semester_id': subject.semester_id,
            'semester_slug': subject.semester.slug,
            'has_syllabus': hasattr(subject, 'syllabus'),
            'year_count': getattr(subject, 'year_count', 0),
            'question_count': getattr(subject, 'question_count', 0),
            'paper_count': getattr(subject, 'paper_count', 0),
            'mock_test_count': getattr(subject, 'mock_test_count', 0),
            'discussion_count': getattr(subject, 'discussion_count', 0),
        }

    def get_queryset(self):
        return Subject.objects.select_related('semester').annotate(
            year_count=Count('years', distinct=True),
            question_count=Count('years__questions', distinct=True),
            paper_count=Count('years__paper', distinct=True),
            mock_test_count=Count('mock_tests', distinct=True),
            discussion_count=Count('discussions', distinct=True),
        ).order_by('semester__id', 'name')

    def get(self, request):
        return Response([
            self.serialize_subject(subject)
            for subject in self.get_queryset()
        ])

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        slug = (request.data.get('slug') or '').strip()
        semester_id = request.data.get('semester_id')

        if not name:
            return Response({'detail': 'Subject name is required.'}, status=400)
        if not semester_id:
            return Response({'detail': 'Semester is required.'}, status=400)

        semester = get_object_or_404(Semester, pk=semester_id)
        subject = Subject(name=name, semester=semester)
        if slug:
            subject.slug = slugify(slug)
        subject.save()
        subject = self.get_queryset().get(id=subject.id)
        return Response(self.serialize_subject(subject), status=201)


class AdminSubjectBulkImportView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def get_value(self, row, *keys):
        normalized = {
            (key or '').strip().lower(): (value or '').strip()
            for key, value in row.items()
        }

        for key in keys:
            value = normalized.get(key)
            if value:
                return value

        return ''

    def resolve_semester(self, row, default_semester_id):
        semester_id = self.get_value(row, 'semester_id')
        semester_slug = self.get_value(row, 'semester_slug')
        semester_name = self.get_value(row, 'semester', 'semester_name')

        if semester_id:
            return Semester.objects.get(pk=semester_id)

        if semester_slug:
            return Semester.objects.get(slug=semester_slug)

        if semester_name:
            semester, _ = Semester.objects.get_or_create(name=semester_name)
            return semester

        if default_semester_id:
            return Semester.objects.get(pk=default_semester_id)

        raise ValueError('Semester is required.')

    def post(self, request):
        upload = request.FILES.get('file')
        default_semester_id = request.data.get('semester_id')

        if not upload:
            return Response({'detail': 'CSV file is required.'}, status=400)

        try:
            decoded = upload.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({'detail': 'CSV must be UTF-8 encoded.'}, status=400)

        reader = csv.DictReader(io.StringIO(decoded))

        if not reader.fieldnames:
            return Response({'detail': 'CSV must include a header row.'}, status=400)

        imported = []
        errors = []
        subject_list_view = AdminSubjectListView()

        for index, row in enumerate(reader, start=2):
            name = self.get_value(row, 'name', 'subject', 'subject_name')
            slug = self.get_value(row, 'slug', 'subject_slug')

            if not name:
                errors.append({'row': index, 'error': 'Subject name is required.'})
                continue

            try:
                semester = self.resolve_semester(row, default_semester_id)
            except Semester.DoesNotExist:
                errors.append({'row': index, 'error': 'Semester was not found.'})
                continue
            except ValueError as exc:
                errors.append({'row': index, 'error': str(exc)})
                continue

            normalized_slug = slugify(slug) if slug else ''
            subject = None

            if normalized_slug:
                subject = Subject.objects.filter(slug=normalized_slug).first()

            if subject is None:
                subject = Subject.objects.filter(
                    semester=semester,
                    name__iexact=name,
                ).first()

            if subject is None:
                subject = Subject(name=name, semester=semester)
            else:
                subject.name = name
                subject.semester = semester

            if normalized_slug:
                subject.slug = normalized_slug

            try:
                subject.save()
            except IntegrityError:
                errors.append({
                    'row': index,
                    'error': 'Subject slug already exists for another subject.',
                })
                continue

            imported.append(
                subject_list_view.serialize_subject(
                    subject_list_view.get_queryset().get(id=subject.id)
                )
            )

        if not imported and errors:
            return Response(
                {
                    'imported_count': 0,
                    'subjects': [],
                    'errors': errors,
                },
                status=400,
            )

        return Response({
            'imported_count': len(imported),
            'subjects': imported,
            'errors': errors,
        })


class AdminSubjectDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        name = request.data.get('name')
        slug = request.data.get('slug')
        semester_id = request.data.get('semester_id')

        if name is not None:
            name = name.strip()
            if not name:
                return Response({'detail': 'Subject name is required.'}, status=400)
            subject.name = name

        if slug is not None:
            subject.slug = slugify(slug.strip()) if slug.strip() else ''

        if semester_id is not None:
            subject.semester = get_object_or_404(Semester, pk=semester_id)

        subject.save()
        return Response({
            'id': subject.id,
            'name': subject.name,
            'slug': subject.slug,
            'semester_id': subject.semester_id,
        })

    def delete(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        subject.delete()
        return Response(status=204)


class AdminSubjectYearListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        years = Year.objects.filter(subject=subject).order_by('-year')

        return Response([
            {
                'id': year.id,
                'year': year.year,
                'question_count': year.questions.count(),
            }
            for year in years
        ])


class AdminSubjectSyllabusView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def serialize_unit(self, unit):
        return {
            'id': unit.id,
            'title': unit.title,
            'slug': unit.slug,
            'duration': unit.duration,
            'content': unit.content,
            'order': unit.order,
        }

    def serialize_section(self, section):
        return {
            'id': section.id,
            'title': section.title,
            'content': section.content,
            'order': section.order,
        }

    def serialize_syllabus(self, syllabus):
        return {
            'id': syllabus.id,
            'subject_id': syllabus.subject_id,
            'pdf_file': syllabus.pdf_file.url if syllabus.pdf_file else None,
            'course_title': syllabus.course_title,
            'course_no': syllabus.course_no,
            'semester_label': syllabus.semester_label,
            'nature': syllabus.nature,
            'full_marks': syllabus.full_marks,
            'pass_marks': syllabus.pass_marks,
            'credit_hours': syllabus.credit_hours,
            'course_description': syllabus.course_description,
            'course_objective': syllabus.course_objective,
            'laboratory_work': syllabus.laboratory_work,
            'text_books': syllabus.text_books,
            'reference_books': syllabus.reference_books,
            'units': [self.serialize_unit(unit) for unit in syllabus.units.all()],
            'sections': [self.serialize_section(section) for section in syllabus.sections.all()],
        }

    def get_syllabus(self, pk):
        subject = get_object_or_404(Subject, pk=pk)
        syllabus, _ = Syllabus.objects.get_or_create(subject=subject)
        return Syllabus.objects.prefetch_related('units', 'sections').get(pk=syllabus.pk)

    def get(self, request, pk):
        return Response(self.serialize_syllabus(self.get_syllabus(pk)))

    def patch(self, request, pk):
        syllabus = self.get_syllabus(pk)
        fields = [
            'course_title',
            'course_no',
            'semester_label',
            'nature',
            'full_marks',
            'pass_marks',
            'credit_hours',
            'course_description',
            'course_objective',
            'laboratory_work',
            'text_books',
            'reference_books',
        ]

        for field in fields:
            if field in request.data:
                setattr(syllabus, field, (request.data.get(field) or '').strip())

        pdf_file = request.FILES.get('pdf_file')
        if pdf_file:
            if not pdf_file.name.lower().endswith('.pdf'):
                return Response({'detail': 'Only PDF syllabus files are allowed.'}, status=400)
            syllabus.pdf_file = pdf_file

        syllabus.save()
        return Response(self.serialize_syllabus(self.get_syllabus(pk)))


class AdminSubjectSyllabusCsvImportView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        subject = get_object_or_404(Subject.objects.select_related('semester'), pk=pk)
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'detail': 'CSV file is required.'}, status=400)
        if not csv_file.name.lower().endswith('.csv'):
            return Response({'detail': 'Only CSV files are allowed.'}, status=400)

        rows = read_uploaded_csv(csv_file)
        subject_rows = choose_subject_csv_rows(subject, rows)
        if not subject_rows:
            return Response({'detail': 'No rows in this CSV match the selected subject.'}, status=400)

        first_row = subject_rows[0]
        imported_units = 0
        imported_sections = 0

        with transaction.atomic():
            syllabus, _ = Syllabus.objects.get_or_create(subject=subject)
            syllabus.course_title = clean_csv_value(first_row.get('course_title')) or subject.name
            syllabus.course_no = clean_csv_value(first_row.get('course_code'))
            syllabus.semester_label = clean_csv_value(first_row.get('semester'))
            syllabus.nature = clean_csv_value(first_row.get('nature'))
            syllabus.full_marks = clean_csv_value(first_row.get('full_marks'))
            syllabus.pass_marks = clean_csv_value(first_row.get('pass_marks'))
            syllabus.credit_hours = clean_csv_value(first_row.get('credit_hrs'))
            syllabus.course_description = ''
            syllabus.course_objective = ''
            syllabus.laboratory_work = ''
            syllabus.text_books = ''
            syllabus.reference_books = ''
            syllabus.save()

            syllabus.units.all().delete()
            syllabus.sections.all().delete()

            section_order = 1
            used_slugs = set()
            for row in subject_rows:
                section = clean_csv_value(row.get('section'))
                section_key = section.lower()
                content = clean_csv_value(row.get('content'))

                if section_key == 'course contents':
                    unit_no = clean_csv_value(row.get('unit_no'))
                    unit_title = clean_csv_value(row.get('unit_title')) or f'Unit {unit_no}'
                    if not unit_no:
                        continue

                    SyllabusUnit.objects.create(
                        syllabus=syllabus,
                        title=unit_title,
                        slug=unique_syllabus_unit_slug(syllabus, unit_title, used_slugs),
                        duration=clean_csv_value(row.get('hours')),
                        content=content,
                        order=parse_csv_order(unit_no),
                    )
                    imported_units += 1
                    continue

                field_name = SYLLABUS_FIELD_SECTIONS.get(section_key)
                if field_name:
                    setattr(syllabus, field_name, append_csv_text(getattr(syllabus, field_name), content))
                    continue

                if content:
                    SyllabusSection.objects.create(
                        syllabus=syllabus,
                        title=section,
                        content=content,
                        order=section_order,
                    )
                    imported_sections += 1
                    section_order += 1

            syllabus.save()

        return Response({
            'imported_units': imported_units,
            'imported_sections': imported_sections,
            'syllabus_id': syllabus.id,
        })


class AdminSyllabusUnitListView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_unit(self, unit):
        return {
            'id': unit.id,
            'title': unit.title,
            'slug': unit.slug,
            'duration': unit.duration,
            'content': unit.content,
            'order': unit.order,
        }

    def get_syllabus(self, subject_pk):
        subject = get_object_or_404(Subject, pk=subject_pk)
        syllabus, _ = Syllabus.objects.get_or_create(subject=subject)
        return syllabus

    def post(self, request, pk):
        syllabus = self.get_syllabus(pk)
        title = (request.data.get('title') or '').strip()
        slug = (request.data.get('slug') or '').strip()
        duration = (request.data.get('duration') or '').strip()
        content = (request.data.get('content') or '').strip()
        order = request.data.get('order') or 0

        if not title:
            return Response({'detail': 'Unit title is required.'}, status=400)

        unit = SyllabusUnit(
            syllabus=syllabus,
            title=title,
            duration=duration,
            content=content,
            order=order,
        )
        if slug:
            unit.slug = slugify(slug)
        unit.save()
        return Response(self.serialize_unit(unit), status=201)


class AdminSyllabusUnitDetailView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_unit(self, unit):
        return {
            'id': unit.id,
            'title': unit.title,
            'slug': unit.slug,
            'duration': unit.duration,
            'content': unit.content,
            'order': unit.order,
        }

    def patch(self, request, pk):
        unit = get_object_or_404(SyllabusUnit, pk=pk)
        for field in ['title', 'duration', 'content']:
            if field in request.data:
                setattr(unit, field, (request.data.get(field) or '').strip())
        if 'slug' in request.data:
            unit.slug = slugify((request.data.get('slug') or '').strip())
        if 'order' in request.data:
            unit.order = request.data.get('order') or 0
        unit.save()
        return Response(self.serialize_unit(unit))

    def delete(self, request, pk):
        unit = get_object_or_404(SyllabusUnit, pk=pk)
        unit.delete()
        return Response(status=204)


class AdminSubjectNoteListView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def serialize_note(self, note):
        return {
            'id': note.id,
            'subject_id': note.subject_id,
            'title': note.title,
            'slug': note.slug,
            'body': note.body,
            'pdf_file': note.pdf_file.url if note.pdf_file else None,
            'unit': note.unit_id,
            'unit_slug': note.unit.slug if note.unit else '',
            'unit_title': note.unit.title if note.unit else '',
            'unit_duration': note.unit.duration if note.unit else '',
            'unit_content': note.unit.content if note.unit else '',
            'credit_name': note.credit_name,
            'credit_designation': note.credit_designation,
            'credit_url': note.credit_url,
            'credit_image': note.credit_image.url if note.credit_image else None,
            'order': note.order,
            'is_published': note.is_published,
            'updated_at': note.updated_at,
        }

    def get(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        notes = Note.objects.filter(subject=subject).select_related('unit')
        return Response([self.serialize_note(note) for note in notes])

    def post(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        pdf_file = request.FILES.get('pdf_file')
        unit_id = request.data.get('unit') or None
        credit_name = (request.data.get('credit_name') or '').strip()
        credit_designation = (request.data.get('credit_designation') or '').strip()
        credit_url = (request.data.get('credit_url') or '').strip()
        credit_image = request.FILES.get('credit_image')

        if not pdf_file:
            return Response({'detail': 'Note PDF file is required.'}, status=400)
        pdf_error = validate_pdf_upload(pdf_file)
        if pdf_error:
            return Response({'detail': pdf_error}, status=400)

        if not unit_id:
            return Response({'detail': 'Choose a syllabus chapter for this note.'}, status=400)
        unit = get_object_or_404(SyllabusUnit, pk=unit_id, syllabus__subject=subject)

        title = derive_note_title(subject, unit, pdf_file)
        slug = build_note_slug(subject, unit, title)
        note, _ = Note.objects.update_or_create(
            subject=subject,
            slug=slug,
            defaults={
                'unit': unit,
                'title': title,
                'body': '',
                'pdf_file': pdf_file,
                'credit_name': credit_name,
                'credit_designation': credit_designation,
                'credit_url': credit_url,
                'credit_image': credit_image,
                'order': unit.order,
                'is_published': True,
            },
        )
        return Response(self.serialize_note(note), status=201)


class AdminSubjectNoteCsvImportView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def find_unit(self, subject, row):
        unit_id = clean_csv_value(row.get('unit_id'))
        if unit_id:
            return get_object_or_404(SyllabusUnit, pk=unit_id, syllabus__subject=subject)

        syllabus = Syllabus.objects.filter(subject=subject).first()
        if not syllabus:
            return None

        unit_slug = clean_csv_value(row.get('unit_slug'))
        if unit_slug:
            unit = SyllabusUnit.objects.filter(syllabus=syllabus, slug=slugify(unit_slug)).first()
            if unit:
                return unit

        unit_no = clean_csv_value(row.get('unit_no'))
        if unit_no:
            unit = SyllabusUnit.objects.filter(syllabus=syllabus, order=parse_csv_order(unit_no)).first()
            if unit:
                return unit

        unit_title = clean_csv_value(row.get('unit_title'))
        if unit_title:
            target = normalize_course_match(unit_title)
            for unit in SyllabusUnit.objects.filter(syllabus=syllabus):
                if normalize_course_match(unit.title) == target:
                    return unit

        return None

    def post(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'detail': 'CSV file is required.'}, status=400)
        if not csv_file.name.lower().endswith('.csv'):
            return Response({'detail': 'Only CSV files are allowed.'}, status=400)

        rows = choose_subject_csv_rows(subject, read_uploaded_csv(csv_file))
        if not rows:
            return Response({'detail': 'No rows in this CSV match the selected subject.'}, status=400)

        imported_count = 0
        errors = []

        for index, row in enumerate(rows, start=2):
            section = clean_csv_value(row.get('section')).lower()
            title = (
                clean_csv_value(row.get('title'))
                or clean_csv_value(row.get('note_title'))
                or clean_csv_value(row.get('unit_title'))
            )
            body = (
                clean_csv_value(row.get('body'))
                or clean_csv_value(row.get('note'))
                or clean_csv_value(row.get('content'))
            )

            if section and section != 'course contents' and not clean_csv_value(row.get('title')) and not clean_csv_value(row.get('note_title')):
                continue
            if not title or not body:
                if body or title:
                    errors.append({'row': index, 'error': 'Both title and body/content are required.'})
                continue

            unit = self.find_unit(subject, row)
            slug = slugify(clean_csv_value(row.get('slug')) or title)
            order = parse_csv_order(row.get('order') or row.get('unit_no'))
            is_published = parse_csv_bool(row.get('is_published'), default=True)
            credit_name = clean_csv_value(row.get('credit_name') or row.get('credit person') or row.get('credit_person'))
            credit_designation = clean_csv_value(row.get('credit_designation') or row.get('designation'))
            credit_url = clean_csv_value(row.get('credit_url') or row.get('credit link') or row.get('credit_link'))

            Note.objects.update_or_create(
                subject=subject,
                slug=slug,
                defaults={
                    'unit': unit,
                    'title': title,
                    'body': body,
                    'credit_name': credit_name,
                    'credit_designation': credit_designation,
                    'credit_url': credit_url,
                    'order': order,
                    'is_published': is_published,
                },
            )
            imported_count += 1

        return Response({
            'imported_count': imported_count,
            'errors': errors,
        })


class AdminNoteDetailView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def serialize_note(self, note):
        return {
            'id': note.id,
            'subject_id': note.subject_id,
            'title': note.title,
            'slug': note.slug,
            'body': note.body,
            'pdf_file': note.pdf_file.url if note.pdf_file else None,
            'unit': note.unit_id,
            'unit_slug': note.unit.slug if note.unit else '',
            'unit_title': note.unit.title if note.unit else '',
            'unit_duration': note.unit.duration if note.unit else '',
            'unit_content': note.unit.content if note.unit else '',
            'credit_name': note.credit_name,
            'credit_designation': note.credit_designation,
            'credit_url': note.credit_url,
            'credit_image': note.credit_image.url if note.credit_image else None,
            'order': note.order,
            'is_published': note.is_published,
            'updated_at': note.updated_at,
        }

    def patch(self, request, pk):
        note = get_object_or_404(Note.objects.select_related('subject', 'unit'), pk=pk)
        pdf_file = request.FILES.get('pdf_file')
        credit_image = request.FILES.get('credit_image')
        pdf_error = validate_pdf_upload(pdf_file)
        if pdf_error:
            return Response({'detail': pdf_error}, status=400)
        if pdf_file:
            note.pdf_file = pdf_file
        if credit_image:
            note.credit_image = credit_image
        if 'credit_name' in request.data:
            note.credit_name = (request.data.get('credit_name') or '').strip()
        if 'credit_designation' in request.data:
            note.credit_designation = (request.data.get('credit_designation') or '').strip()
        if 'credit_url' in request.data:
            note.credit_url = (request.data.get('credit_url') or '').strip()
        if 'unit' in request.data:
            unit_id = request.data.get('unit') or None
            note.unit = (
                get_object_or_404(SyllabusUnit, pk=unit_id, syllabus__subject=note.subject)
                if unit_id
                else None
            )
        if not note.pdf_file:
            return Response({'detail': 'Note PDF file is required.'}, status=400)
        note.title = derive_note_title(note.subject, note.unit, note.pdf_file)
        note.slug = build_note_slug(note.subject, note.unit, note.title)
        if Note.objects.filter(subject=note.subject, slug=note.slug).exclude(pk=note.pk).exists():
            return Response({'detail': 'A note already exists for this chapter.'}, status=400)
        note.body = ''
        note.order = note.unit.order if note.unit else 0
        note.is_published = True
        note.save()
        return Response(self.serialize_note(Note.objects.select_related('unit').get(pk=note.pk)))

    def delete(self, request, pk):
        note = get_object_or_404(Note, pk=pk)
        note.delete()
        return Response(status=204)


class AdminQuestionListView(APIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Question.objects.select_related(
            'year',
            'year__subject',
            'year__subject__semester',
            'section',
        ).order_by('year__subject__semester__id', 'year__subject__name', '-year__year', 'order', 'id')

    def serialize_question(self, question):
        return {
            'id': question.id,
            'source_question_id': question.source_question_id,
            'source_url': question.source_url,
            'answer_source_url': question.answer_source_url,
            'answer_image_paths': question.answer_image_paths,
            'question_text': question.question_text,
            'answer_text': question.answer_text,
            'marks': question.marks,
            'order': question.order,
            'section': question.section.title if question.section else '',
            'year': question.year.year,
            'year_id': question.year_id,
            'subject_id': question.year.subject_id,
            'subject': question.year.subject.name,
            'subject_slug': question.year.subject.slug,
            'semester': question.year.subject.semester.name,
            'semester_slug': question.year.subject.semester.slug,
        }

    def get(self, request):
        queryset = self.get_queryset()
        semester_id = request.query_params.get('semester_id')
        subject_id = request.query_params.get('subject_id')
        year_value = (request.query_params.get('year') or '').strip()
        query = (request.query_params.get('q') or '').strip()

        if semester_id:
            queryset = queryset.filter(year__subject__semester_id=semester_id)

        if subject_id:
            queryset = queryset.filter(year__subject_id=subject_id)

        if year_value:
            queryset = queryset.filter(year__year=year_value)

        if query:
            queryset = queryset.filter(question_text__icontains=query)

        return Response([
            self.serialize_question(question)
            for question in queryset[:250]
        ])

    def post(self, request):
        subject_id = request.data.get('subject_id')
        year_value = (request.data.get('year') or '').strip()
        question_text = (request.data.get('question_text') or '').strip()
        answer_text = (request.data.get('answer_text') or '').strip()
        marks = (request.data.get('marks') or '').strip()
        order = request.data.get('order') or 0

        if not subject_id:
            return Response({'detail': 'Subject is required.'}, status=400)
        if not year_value:
            return Response({'detail': 'Year is required.'}, status=400)
        if not question_text:
            return Response({'detail': 'Question text is required.'}, status=400)
        if not answer_text:
            return Response({'detail': 'Answer text is required.'}, status=400)

        subject = get_object_or_404(Subject, pk=subject_id)
        year, _ = Year.objects.get_or_create(subject=subject, year=year_value)
        question = Question.objects.create(
            year=year,
            question_text=question_text,
            answer_text=answer_text,
            marks=marks,
            order=order,
        )
        return Response(self.serialize_question(question), status=201)


class AdminQuestionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        question = get_object_or_404(AdminQuestionListView().get_queryset(), pk=pk)
        return Response(AdminQuestionListView().serialize_question(question))

    def patch(self, request, pk):
        question = get_object_or_404(Question.objects.select_related('year'), pk=pk)
        subject_id = request.data.get('subject_id')
        year_value = request.data.get('year')

        if subject_id is not None or year_value is not None:
            subject = (
                get_object_or_404(Subject, pk=subject_id)
                if subject_id is not None
                else question.year.subject
            )
            year_name = (
                year_value.strip()
                if isinstance(year_value, str)
                else question.year.year
            )
            if not year_name:
                return Response({'detail': 'Year is required.'}, status=400)
            question.year, _ = Year.objects.get_or_create(
                subject=subject,
                year=year_name,
            )

        for field in [
            'source_question_id',
            'source_url',
            'answer_source_url',
            'answer_image_paths',
            'question_text',
            'answer_text',
            'marks',
        ]:
            if field in request.data:
                value = (request.data.get(field) or '').strip()
                if field in ['question_text', 'answer_text'] and not value:
                    return Response(
                        {'detail': f'{field.replace("_", " ").title()} is required.'},
                        status=400,
                    )
                setattr(question, field, value)

        if 'order' in request.data:
            question.order = request.data.get('order') or 0

        question.save()
        question = AdminQuestionListView().get_queryset().get(id=question.id)
        return Response(AdminQuestionListView().serialize_question(question))

    def delete(self, request, pk):
        question = get_object_or_404(Question, pk=pk)
        question.delete()
        return Response(status=204)


class AdminQuestionBulkImportView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def get_value(self, row, *keys):
        normalized = {
            compact_match_value(key): clean_csv_value(value)
            for key, value in row.items()
        }

        for key in keys:
            value = normalized.get(compact_match_value(key))
            if value:
                return value

        return ''

    def resolve_subject(self, row, default_subject_id, default_semester_id):
        subject_id = self.get_value(row, 'subject_id')
        subject_slug = self.get_value(row, 'subject_slug', 'slug')
        subject_name = self.get_value(row, 'subject', 'subject_name')
        semester = self.resolve_semester(row, default_semester_id)

        if subject_id:
            return Subject.objects.get(pk=subject_id)

        if subject_slug:
            return Subject.objects.get(slug=subject_slug)

        if subject_name:
            subjects = Subject.objects.filter(name__iexact=subject_name)

            if semester:
                subjects = subjects.filter(semester=semester)

            count = subjects.count()
            if count == 1:
                return subjects.first()
            if count > 1:
                raise ValueError(
                    f"Multiple subjects named '{subject_name}'. Add subject_slug or choose a semester."
                )
            raise Subject.DoesNotExist

        if default_subject_id:
            return Subject.objects.get(pk=default_subject_id)

        raise ValueError('Subject is required.')

    def resolve_semester(self, row, default_semester_id):
        semester_id = self.get_value(row, 'semester_id')
        semester_slug = self.get_value(row, 'semester_slug')
        semester_name = self.get_value(row, 'semester', 'semester_name')

        if semester_id:
            return Semester.objects.get(pk=semester_id)

        if semester_slug:
            return Semester.objects.get(slug=semester_slug)

        if semester_name:
            semester, _ = Semester.objects.get_or_create(name=semester_name)
            return semester

        if default_semester_id:
            return Semester.objects.get(pk=default_semester_id)

        return None

    def resolve_or_create_subject(self, row, default_subject_id, default_semester_id):
        try:
            return self.resolve_subject(row, default_subject_id, default_semester_id)
        except Subject.DoesNotExist:
            subject_slug = self.get_value(row, 'subject_slug', 'slug')
            subject_name = self.get_value(row, 'subject', 'subject_name')
            semester = self.resolve_semester(row, default_semester_id)

            if not subject_name or not semester:
                raise

            subject = Subject(name=subject_name, semester=semester)
            if subject_slug:
                subject.slug = slugify(subject_slug)
            subject.save()
            return subject

    def parse_answers_file(self, upload):
        if not upload:
            return {}

        try:
            decoded = upload.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ValueError('answers.csv must be UTF-8 encoded.')

        reader = csv.DictReader(io.StringIO(decoded))
        answers = {}

        for row in reader:
            question_id = self.get_value(row, 'question_id')
            if not question_id:
                continue

            answer_markdown = self.get_value(row, 'answer_markdown', 'answer_text', 'answer')
            image_paths = self.get_value(row, 'image_paths')
            answer_source_url = self.get_value(row, 'answer_source_url', 'source_url')

            answers[question_id] = {
                'answer_text': answer_markdown,
                'answer_image_paths': image_paths,
                'answer_source_url': answer_source_url,
            }

        return answers

    def get_existing_question(self, year, source_question_id, question_text):
        if source_question_id:
            question = Question.objects.select_related(
                'year',
                'year__subject',
                'year__subject__semester',
                'section',
            ).filter(
                source_question_id=source_question_id,
            ).first()
            if question:
                return question

        if not year or not question_text:
            return None

        return Question.objects.filter(
            year=year,
            question_text=question_text,
        ).first()

    def post(self, request):
        upload = request.FILES.get('file')
        answers_upload = request.FILES.get('answers_file')
        default_subject_id = request.data.get('subject_id')
        default_semester_id = request.data.get('semester_id')
        default_year = (request.data.get('year') or '').strip()

        if not upload:
            return Response({'detail': 'CSV file is required.'}, status=400)

        try:
            decoded = upload.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({'detail': 'CSV must be UTF-8 encoded.'}, status=400)

        reader = csv.DictReader(io.StringIO(decoded))

        if not reader.fieldnames:
            return Response({'detail': 'CSV must include a header row.'}, status=400)

        try:
            answers_by_question_id = self.parse_answers_file(answers_upload)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)

        imported = []
        errors = []

        for index, row in enumerate(reader, start=2):
            question_id = self.get_value(row, 'question_id', 'source_question_id')
            existing_question = self.get_existing_question(None, question_id, '')
            question_text = (
                self.get_value(row, 'question_text', 'question', 'prompt')
                or (existing_question.question_text if existing_question else '')
            )
            answer_data = answers_by_question_id.get(question_id, {})
            answer_text = (
                self.get_value(row, 'answer_text', 'answer', 'answer_markdown')
                or answer_data.get('answer_text', '')
                or (existing_question.answer_text if existing_question else '')
            )
            year_value = (
                self.get_value(row, 'year')
                or default_year
                or (existing_question.year.year if existing_question else '')
            )
            marks = self.get_value(row, 'marks') or (
                existing_question.marks if existing_question else ''
            )
            order_value = self.get_value(row, 'order')
            question_number = self.get_value(row, 'question_number')
            section_title = self.get_value(row, 'section', 'group')
            exam_time = self.get_value(row, 'exam_time')
            instructions = self.get_value(row, 'instructions')
            source_url = self.get_value(row, 'source_url', 'question_source_url') or (
                existing_question.source_url if existing_question else ''
            )
            answer_source_url = (
                self.get_value(row, 'answer_source_url')
                or answer_data.get('answer_source_url', '')
                or (existing_question.answer_source_url if existing_question else '')
            )
            answer_image_paths = (
                self.get_value(row, 'image_paths', 'answer_image_paths')
                or answer_data.get('answer_image_paths', '')
                or (existing_question.answer_image_paths if existing_question else '')
            )

            if not question_text:
                errors.append({
                    'row': index,
                    'error': 'Question text is required unless question_id matches an existing question.',
                })
                continue

            if not year_value:
                errors.append({'row': index, 'error': 'Year is required.'})
                continue

            if existing_question and not any([
                self.get_value(row, 'subject_id'),
                self.get_value(row, 'subject_slug', 'slug'),
                self.get_value(row, 'subject', 'subject_name'),
                default_subject_id,
            ]):
                subject = existing_question.year.subject
            else:
                try:
                    subject = self.resolve_or_create_subject(
                        row,
                        default_subject_id,
                        default_semester_id,
                    )
                except Subject.DoesNotExist:
                    errors.append({'row': index, 'error': 'Subject was not found.'})
                    continue
                except Semester.DoesNotExist:
                    errors.append({'row': index, 'error': 'Semester was not found.'})
                    continue
                except ValueError as exc:
                    errors.append({'row': index, 'error': str(exc)})
                    continue

            try:
                order = int(order_value or question_number or (
                    existing_question.order if existing_question else 0
                ))
            except ValueError:
                order = 0

            year, _ = Year.objects.get_or_create(subject=subject, year=year_value)
            update_fields = []
            if exam_time and year.time != exam_time:
                year.time = exam_time
                update_fields.append('time')
            if instructions and year.instructions != instructions:
                year.instructions = instructions
                update_fields.append('instructions')
            if update_fields:
                year.save(update_fields=update_fields)

            section = None
            if section_title:
                section, _ = QuestionSection.objects.get_or_create(
                    year=year,
                    title=section_title[:80],
                    defaults={'order': 0},
                )

            question = self.get_existing_question(year, question_id, question_text)
            existing_section = (
                question.section
                if question and question.section and question.section.year_id == year.id
                else None
            )
            question_values = {
                'year': year,
                'section': section if section_title else existing_section,
                'source_question_id': question_id or (
                    question.source_question_id if question else ''
                ),
                'source_url': source_url,
                'answer_source_url': answer_source_url,
                'answer_image_paths': answer_image_paths,
                'question_text': question_text,
                'answer_text': answer_text,
                'marks': marks,
                'order': order,
            }
            if question:
                for field, value in question_values.items():
                    setattr(question, field, value)
                question.save()
            else:
                question = Question.objects.create(**question_values)
            imported.append(AdminQuestionListView().serialize_question(question))

        if not imported and errors:
            return Response(
                {
                    'imported_count': 0,
                    'questions': [],
                    'errors': errors,
                },
                status=400,
            )

        return Response({
            'imported_count': len(imported),
            'questions': imported,
            'errors': errors,
        })


class AdminAnswerContributionListView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_contribution(self, contribution):
        return {
            'id': contribution.id,
            'question_id': contribution.question_id,
            'question_text': contribution.question.question_text,
            'subject': contribution.question.year.subject.name,
            'subject_slug': contribution.question.year.subject.slug,
            'semester': contribution.question.year.subject.semester.name,
            'year': contribution.question.year.year,
            'username': contribution.user.username,
            'answer_text': contribution.answer_text,
            'image': contribution.image.url if contribution.image else '',
            'status': contribution.status,
            'rejection_reason': contribution.rejection_reason,
            'reviewed_by': (
                contribution.reviewed_by.username
                if contribution.reviewed_by
                else ''
            ),
            'reviewed_at': contribution.reviewed_at,
            'created_at': contribution.created_at,
        }

    def get_queryset(self):
        return AnswerContribution.objects.select_related(
            'question',
            'question__year',
            'question__year__subject',
            'question__year__subject__semester',
            'user',
            'reviewed_by',
        )

    def get(self, request):
        contributions = self.get_queryset()
        status_filter = (request.query_params.get('status') or '').strip()

        if status_filter:
            contributions = contributions.filter(status=status_filter)

        return Response([
            self.serialize_contribution(contribution)
            for contribution in contributions[:250]
        ])


class AdminAnswerContributionDetailView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def notify_status_change(self, contribution):
        subject = contribution.question.year.subject
        question_text = ' '.join(contribution.question.question_text.split())
        if len(question_text) > 90:
            question_text = f'{question_text[:87]}...'

        if contribution.status == AnswerContribution.STATUS_APPROVED:
            message = f'Your answer contribution for "{question_text}" was accepted.'
        elif contribution.status == AnswerContribution.STATUS_REJECTED:
            message = (
                f'Your answer contribution for "{question_text}" was rejected. '
                f'Reason: {contribution.rejection_reason}'
            )
        else:
            return

        Notification.objects.create(
            user=contribution.user,
            type=Notification.TYPE_CONTRIBUTION,
            message=message,
            link_path=f'/semester/{subject.semester.slug}/subject/{subject.slug}',
        )

    def patch(self, request, pk):
        contribution = get_object_or_404(AnswerContribution, pk=pk)
        original_status = contribution.status
        status_value = (request.data.get('status') or '').strip()
        rejection_reason = str(request.data.get('rejection_reason') or '').strip()
        valid_statuses = {
            AnswerContribution.STATUS_PENDING,
            AnswerContribution.STATUS_APPROVED,
            AnswerContribution.STATUS_REJECTED,
        }
        update_fields = []
        should_notify = False

        if 'answer_text' in request.data:
            contribution.answer_text = (request.data.get('answer_text') or '').strip()
            update_fields.append('answer_text')

        remove_image = (
            'remove_image' in request.data
            and parse_csv_bool(request.data.get('remove_image'), default=False)
        )
        image = request.FILES.get('image')

        if image:
            try:
                Image.open(image).verify()
                image.seek(0)
            except (OSError, UnidentifiedImageError):
                return Response({'detail': 'Upload a valid image file.'}, status=400)

            if contribution.image:
                contribution.image.delete(save=False)
            contribution.image = image
            update_fields.append('image')
        elif remove_image:
            if contribution.image:
                contribution.image.delete(save=False)
            contribution.image = None
            update_fields.append('image')

        if not contribution.answer_text and not contribution.image:
            return Response(
                {'detail': 'Answer text or image is required.'},
                status=400,
            )

        if 'status' in request.data:
            if status_value not in valid_statuses:
                return Response({'detail': 'A valid status is required.'}, status=400)

            contribution.status = status_value
            update_fields.append('status')
            if status_value == AnswerContribution.STATUS_PENDING:
                contribution.reviewed_by = None
                contribution.reviewed_at = None
                contribution.rejection_reason = ''
                update_fields.append('rejection_reason')
            else:
                if status_value == AnswerContribution.STATUS_REJECTED:
                    if not rejection_reason:
                        return Response(
                            {'detail': 'Rejection reason is required.'},
                            status=400,
                        )
                    contribution.rejection_reason = rejection_reason
                    update_fields.append('rejection_reason')
                elif contribution.rejection_reason:
                    contribution.rejection_reason = ''
                    update_fields.append('rejection_reason')
                contribution.reviewed_by = request.user
                contribution.reviewed_at = timezone.now()
                should_notify = status_value != original_status
            update_fields.extend(['reviewed_by', 'reviewed_at'])
        elif 'rejection_reason' in request.data:
            if contribution.status != AnswerContribution.STATUS_REJECTED:
                return Response(
                    {
                        'detail': (
                            'Rejection reason can only be set when rejecting '
                            'a contribution.'
                        ),
                    },
                    status=400,
                )
            if not rejection_reason:
                return Response(
                    {'detail': 'Rejection reason is required.'},
                    status=400,
                )
            contribution.rejection_reason = rejection_reason
            update_fields.append('rejection_reason')

        if update_fields:
            update_fields.append('updated_at')
            with transaction.atomic():
                contribution.save(update_fields=sorted(set(update_fields)))
                if should_notify:
                    self.notify_status_change(contribution)
        contribution = AdminAnswerContributionListView().get_queryset().get(
            pk=contribution.pk,
        )
        return Response(
            AdminAnswerContributionListView().serialize_contribution(
                contribution,
            )
        )


class AdminUserListView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_user(self, user):
        user.refresh_expired_suspension(save=True)
        return {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'is_active': user.is_active,
            'account_status': user.account_status,
            'suspended_until': user.suspended_until,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
        }

    def get(self, request):
        request.user.__class__.objects.filter(
            account_status=request.user.__class__.STATUS_SUSPENDED,
            suspended_until__lte=timezone.now(),
        ).update(
            account_status=request.user.__class__.STATUS_ACTIVE,
            is_active=True,
            suspended_until=None,
        )
        users = request.user.__class__.objects.order_by('-date_joined')
        return Response([self.serialize_user(user) for user in users[:250]])


class AdminUserDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        user = get_object_or_404(request.user.__class__, pk=pk)
        if user.is_superuser and not request.user.is_superuser:
            return Response(
                {'detail': 'Only a superuser can change a superuser account.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if 'is_staff' in request.data or 'is_superuser' in request.data:
            return Response(
                {'detail': 'Staff access cannot be changed from this endpoint.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        update_fields = []

        account_status = request.data.get('account_status') or request.data.get('action')
        if account_status:
            account_status = str(account_status).strip().lower()
            account_status = {
                'activate': request.user.__class__.STATUS_ACTIVE,
                'suspend': request.user.__class__.STATUS_SUSPENDED,
                'block': request.user.__class__.STATUS_BLOCKED,
            }.get(account_status, account_status)
            if account_status not in {
                request.user.__class__.STATUS_ACTIVE,
                request.user.__class__.STATUS_SUSPENDED,
                request.user.__class__.STATUS_BLOCKED,
            }:
                return Response(
                    {'detail': 'Use active, suspended, blocked, activate, suspend, or block.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user == request.user and account_status != request.user.__class__.STATUS_ACTIVE:
                return Response(
                    {'detail': 'You cannot suspend or block your own account.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            suspended_until = None
            if account_status == request.user.__class__.STATUS_SUSPENDED:
                suspend_days_value = request.data.get('suspend_days')
                if suspend_days_value not in [None, '']:
                    try:
                        suspend_days = int(suspend_days_value)
                    except (TypeError, ValueError):
                        return Response(
                            {'detail': 'suspend_days must be a whole number.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if suspend_days < 1 or suspend_days > 3650:
                        return Response(
                            {'detail': 'suspend_days must be between 1 and 3650.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    suspended_until = timezone.now() + timezone.timedelta(
                        days=suspend_days,
                    )
                else:
                    suspended_until_value = (request.data.get('suspended_until') or '').strip()

                if suspended_until is None and suspended_until_value:
                    suspended_until = parse_datetime(suspended_until_value)
                    if suspended_until is None:
                        return Response(
                            {'detail': 'suspended_until must be a valid ISO date-time.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if timezone.is_naive(suspended_until):
                        suspended_until = timezone.make_aware(
                            suspended_until,
                            timezone.get_current_timezone(),
                        )
                    if suspended_until <= timezone.now():
                        return Response(
                            {'detail': 'suspended_until must be in the future.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

            user.set_account_status(account_status, suspended_until=suspended_until)
            update_fields.extend([
                'account_status',
                'is_active',
                'active_token',
                'suspended_until',
            ])

        if not update_fields:
            return Response(AdminUserListView().serialize_user(user))

        user.save(update_fields=sorted(set(update_fields)))
        return Response(AdminUserListView().serialize_user(user))

    def delete(self, request, pk):
        user = get_object_or_404(request.user.__class__, pk=pk)
        if user == request.user:
            return Response(
                {'detail': 'You cannot delete your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.is_superuser and not request.user.is_superuser:
            return Response(
                {'detail': 'Only a superuser can delete a superuser account.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminDiscussionListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        discussions = Discussion.objects.select_related('user', 'subject', 'subject__semester').prefetch_related('replies')[:250]
        return Response([
            {
                'id': discussion.id,
                'title': discussion.title,
                'body': discussion.body,
                'username': discussion.user.username,
                'subject': discussion.subject.name,
                'semester': discussion.subject.semester.name,
                'reply_count': discussion.replies.count(),
                'created_at': discussion.created_at,
            }
            for discussion in discussions
        ])


class AdminDiscussionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        discussion = get_object_or_404(Discussion, pk=pk)
        discussion.delete()
        return Response(status=204)


class AdminTestimonialListView(APIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Testimonial.objects.select_related('user', 'reviewed_by')

    def get(self, request):
        testimonials = self.get_queryset()
        status_filter = (request.query_params.get('status') or '').strip()

        if status_filter:
            testimonials = testimonials.filter(status=status_filter)

        serializer = TestimonialSerializer(testimonials[:250], many=True)
        return Response(serializer.data)


class AdminTestimonialDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        testimonial = get_object_or_404(Testimonial, pk=pk)
        status_value = (request.data.get('status') or '').strip()
        valid_statuses = {
            Testimonial.STATUS_PENDING,
            Testimonial.STATUS_APPROVED,
            Testimonial.STATUS_REJECTED,
        }

        if status_value not in valid_statuses:
            return Response({'detail': 'A valid status is required.'}, status=400)

        testimonial.status = status_value
        if status_value == Testimonial.STATUS_PENDING:
            testimonial.reviewed_by = None
            testimonial.reviewed_at = None
        else:
            testimonial.reviewed_by = request.user
            testimonial.reviewed_at = timezone.now()
        testimonial.save(
            update_fields=[
                'status',
                'reviewed_by',
                'reviewed_at',
                'updated_at',
            ]
        )
        testimonial = AdminTestimonialListView().get_queryset().get(
            pk=testimonial.pk,
        )
        return Response(TestimonialSerializer(testimonial).data)

    def delete(self, request, pk):
        testimonial = get_object_or_404(Testimonial, pk=pk)
        testimonial.delete()
        return Response(status=204)


class AdminNotificationListView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_notification(self, notification):
        return {
            'id': notification.id,
            'username': notification.user.username,
            'type': notification.type,
            'message': notification.message,
            'link_path': notification.link_path,
            'is_read': notification.is_read,
            'created_at': notification.created_at,
        }

    def get(self, request):
        notifications = Notification.objects.select_related('user').order_by('-created_at')[:250]
        return Response([
            self.serialize_notification(notification)
            for notification in notifications
        ])

    def post(self, request):
        message = str(request.data.get('message') or '').strip()
        link_path = str(request.data.get('link_path') or '').strip()
        recipient = str(
            request.data.get('recipient')
            or request.data.get('target')
            or ('user' if request.data.get('user_id') else 'all')
        ).strip().lower()

        if not message:
            return Response({'detail': 'Message is required.'}, status=400)

        if len(link_path) > 255:
            return Response(
                {'detail': 'Link path must be 255 characters or fewer.'},
                status=400,
            )

        if link_path and not link_path.startswith('/'):
            return Response(
                {'detail': 'Link path must start with /.'},
                status=400,
            )

        User = request.user.__class__
        if recipient in {'user', 'specific'}:
            user_id = request.data.get('user_id')
            if not user_id:
                return Response(
                    {'detail': 'user_id is required for a specific user.'},
                    status=400,
                )
            users = [get_object_or_404(User, pk=user_id)]
        elif recipient in {'all', 'users'}:
            users = list(User.objects.filter(is_active=True).order_by('id'))
        else:
            return Response(
                {'detail': 'Recipient must be all or user.'},
                status=400,
            )

        if not users:
            return Response(
                {'detail': 'No active users were found.'},
                status=400,
            )

        with transaction.atomic():
            notifications = [
                Notification.objects.create(
                    user=user,
                    type=Notification.TYPE_CUSTOM,
                    message=message,
                    link_path=link_path,
                )
                for user in users
            ]

        return Response(
            {
                'sent_count': len(notifications),
                'notifications': [
                    self.serialize_notification(notification)
                    for notification in notifications[:250]
                ],
            },
            status=status.HTTP_201_CREATED,
        )


class AdminNotificationDetailView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk)
        notification.delete()
        return Response(status=204)


class AdminMockTestListView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_mock_test(self, mock_test):
        return {
            'id': mock_test.id,
            'title': mock_test.title,
            'subject_id': mock_test.subject_id,
            'subject': mock_test.subject.name,
            'semester': mock_test.subject.semester.name,
            'duration_minutes': mock_test.duration_minutes,
            'total_marks': mock_test.total_marks,
            'is_active': mock_test.is_active,
            'question_count': mock_test.questions.count(),
            'attempt_count': mock_test.results.count(),
        }

    def get_queryset(self):
        return MockTest.objects.select_related('subject', 'subject__semester').prefetch_related('questions', 'results').order_by('subject__semester__id', 'subject__name', 'title')

    def get(self, request):
        return Response([self.serialize_mock_test(test) for test in self.get_queryset()[:250]])

    def post(self, request):
        subject = get_object_or_404(Subject, pk=request.data.get('subject_id'))
        title = (request.data.get('title') or '').strip()
        if not title:
            return Response({'detail': 'Title is required.'}, status=400)

        mock_test = MockTest.objects.create(
            subject=subject,
            title=title,
            duration_minutes=request.data.get('duration_minutes') or 30,
            total_marks=request.data.get('total_marks') or 10,
            is_active=bool(request.data.get('is_active', True)),
        )
        return Response(self.serialize_mock_test(mock_test), status=201)


class AdminMockTestCsvImportView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        subject = get_object_or_404(Subject, pk=request.data.get('subject_id'))
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'detail': 'CSV file is required.'}, status=400)
        if not csv_file.name.lower().endswith('.csv'):
            return Response({'detail': 'Only CSV files are allowed.'}, status=400)

        rows = read_uploaded_csv(csv_file)
        questions = []
        errors = []

        for index, row in enumerate(rows, start=2):
            question_text = get_csv_row_value(row, 'question_text', 'question', 'prompt')
            option_a = get_csv_row_value(row, 'option_a', 'option a', 'a')
            option_b = get_csv_row_value(row, 'option_b', 'option b', 'b')
            option_c = get_csv_row_value(row, 'option_c', 'option c', 'c')
            option_d = get_csv_row_value(row, 'option_d', 'option d', 'd')
            correct_option = get_csv_row_value(
                row,
                'correct_option',
                'correct answer',
                'correct',
                'answer',
            )[:1].upper()

            if not all([question_text, option_a, option_b, option_c, option_d]):
                errors.append(f'Row {index}: question and all four options are required.')
                continue
            if correct_option not in {'A', 'B', 'C', 'D'}:
                errors.append(f'Row {index}: correct answer must be A, B, C, or D.')
                continue

            questions.append(MockTestQuestion(
                question_text=question_text,
                option_a=option_a,
                option_b=option_b,
                option_c=option_c,
                option_d=option_d,
                correct_option=correct_option,
                marks=1,
            ))

        if not questions:
            return Response({
                'detail': 'No valid mock questions found in CSV.',
                'errors': errors,
            }, status=400)

        with transaction.atomic():
            mock_test = MockTest.objects.create(
                subject=subject,
                title=f'{subject.name} Mock Test',
                duration_minutes=max(1, int(len(questions) * 1.5 + 0.9999)),
                total_marks=len(questions),
                is_active=True,
            )
            for question in questions:
                question.mock_test = mock_test
            MockTestQuestion.objects.bulk_create(questions)

        data = AdminMockTestListView().serialize_mock_test(mock_test)
        data['imported_count'] = len(questions)
        data['errors'] = errors
        return Response(data, status=201)


class AdminMockTestDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        mock_test = get_object_or_404(MockTest, pk=pk)
        if 'subject_id' in request.data:
            mock_test.subject = get_object_or_404(Subject, pk=request.data.get('subject_id'))
        for field in ['title', 'duration_minutes', 'total_marks', 'is_active']:
            if field in request.data:
                setattr(mock_test, field, request.data.get(field))
        mock_test.save()
        return Response(AdminMockTestListView().serialize_mock_test(mock_test))

    def delete(self, request, pk):
        mock_test = get_object_or_404(MockTest, pk=pk)
        mock_test.delete()
        return Response(status=204)


class AdminMockTestQuestionListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        mock_test = get_object_or_404(MockTest, pk=pk)
        return Response([
            {
                'id': question.id,
                'question_text': question.question_text,
                'option_a': question.option_a,
                'option_b': question.option_b,
                'option_c': question.option_c,
                'option_d': question.option_d,
                'correct_option': question.correct_option,
                'marks': question.marks,
            }
            for question in mock_test.questions.all()
        ])

    def post(self, request, pk):
        mock_test = get_object_or_404(MockTest, pk=pk)
        question_text = (request.data.get('question_text') or '').strip()
        if not question_text:
            return Response({'detail': 'Question text is required.'}, status=400)
        question = MockTestQuestion.objects.create(
            mock_test=mock_test,
            question_text=question_text,
            option_a=request.data.get('option_a') or '',
            option_b=request.data.get('option_b') or '',
            option_c=request.data.get('option_c') or '',
            option_d=request.data.get('option_d') or '',
            correct_option=request.data.get('correct_option') or 'A',
            marks=request.data.get('marks') or 1,
        )
        return Response({'id': question.id}, status=201)


class AdminMockTestQuestionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_question(self, question):
        return {
            'id': question.id,
            'question_text': question.question_text,
            'option_a': question.option_a,
            'option_b': question.option_b,
            'option_c': question.option_c,
            'option_d': question.option_d,
            'correct_option': question.correct_option,
            'marks': question.marks,
        }

    def patch(self, request, pk):
        question = get_object_or_404(MockTestQuestion, pk=pk)

        for field in [
            'question_text',
            'option_a',
            'option_b',
            'option_c',
            'option_d',
        ]:
            if field in request.data:
                value = (request.data.get(field) or '').strip()
                if not value:
                    return Response(
                        {'detail': f'{field.replace("_", " ").title()} is required.'},
                        status=400,
                    )
                setattr(question, field, value)

        if 'correct_option' in request.data:
            correct_option = (request.data.get('correct_option') or '').strip().upper()[:1]
            if correct_option not in {'A', 'B', 'C', 'D'}:
                return Response(
                    {'detail': 'Correct option must be A, B, C, or D.'},
                    status=400,
                )
            question.correct_option = correct_option

        if 'marks' in request.data:
            try:
                marks = int(request.data.get('marks') or 1)
            except (TypeError, ValueError):
                return Response({'detail': 'Marks must be a whole number.'}, status=400)
            if marks < 1:
                return Response({'detail': 'Marks must be at least 1.'}, status=400)
            question.marks = marks

        question.save()
        return Response(self.serialize_question(question))

    def delete(self, request, pk):
        question = get_object_or_404(MockTestQuestion, pk=pk)
        question.delete()
        return Response(status=204)
