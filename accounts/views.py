import csv
import io

from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.utils.text import slugify
from academics.models import (
    Discussion,
    DiscussionReply,
    MockTest,
    MockTestQuestion,
    MockTestResult,
    Question,
    QuestionPaper,
    QuestionSection,
    Semester,
    Subject,
    Syllabus,
    Year,
)
from .models import (
    Notification,
    PaymentTransaction,
    SubscriptionPlan,
    UserSubscription,
)
from .serializers import (
    KhaltiInitiateSerializer,
    KhaltiVerifySerializer,
    NotificationSerializer,
    PaymentTransactionSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
)
from .services import (
    KhaltiConfigurationError,
    KhaltiPaymentError,
    apply_khalti_lookup,
    initiate_khalti_payment,
    lookup_khalti_payment,
)


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


class SubscriptionPlanListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True)


class SubscriptionPlanDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubscriptionPlanSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True)


class MySubscriptionListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSubscriptionSerializer

    def get_queryset(self):
        return UserSubscription.objects.filter(
            user=self.request.user,
        ).select_related('plan')


class KhaltiInitiateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = KhaltiInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            plan = SubscriptionPlan.objects.get(
                slug=data['plan_slug'],
                is_active=True,
            )
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {'detail': 'Selected subscription plan was not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        amount_paisa = int(plan.price * 100)
        purchase_order_id = f"sub-{request.user.id}-{get_random_string(12)}"
        payment = PaymentTransaction.objects.create(
            user=request.user,
            plan=plan,
            amount=plan.price,
            amount_paisa=amount_paisa,
            purchase_order_id=purchase_order_id,
            purchase_order_name=f"{plan.name} subscription",
            customer_name=data['customer_name'],
            customer_email=data.get('customer_email', ''),
            customer_phone=data.get('customer_phone', ''),
        )

        try:
            initiate_khalti_payment(payment)
        except KhaltiConfigurationError as exc:
            payment.status = PaymentTransaction.STATUS_FAILED
            payment.save(update_fields=['status', 'updated_at'])
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except KhaltiPaymentError as exc:
            payment.status = PaymentTransaction.STATUS_FAILED
            payment.save(update_fields=['status', 'updated_at'])
            return Response(
                {'detail': 'Khalti initiation failed.', 'error': str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(PaymentTransactionSerializer(payment).data)


class KhaltiVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = KhaltiVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pidx = serializer.validated_data['pidx']

        try:
            payment = PaymentTransaction.objects.select_related(
                'plan',
                'user',
                'subscription',
            ).get(pidx=pidx, user=request.user)
        except PaymentTransaction.DoesNotExist:
            return Response(
                {'detail': 'Payment transaction was not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            lookup_data = lookup_khalti_payment(pidx)
        except KhaltiConfigurationError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except KhaltiPaymentError as exc:
            return Response(
                {'detail': 'Khalti lookup failed.', 'error': str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment = apply_khalti_lookup(payment, lookup_data)
        return Response(PaymentTransactionSerializer(payment).data)


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
        payment_statuses = dict(
            PaymentTransaction.objects.values_list('status').annotate(
                count=Count('id')
            )
        )
        payments_by_day = {
            item['day'].isoformat(): item
            for item in PaymentTransaction.objects.filter(
                created_at__date__gte=start_date,
            )
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(
                count=Count('id'),
                revenue=Sum('amount'),
            )
            .order_by('day')
        }
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
            payment_day = payments_by_day.get(key, {})
            timeline.append({
                'date': key,
                'payments': payment_day.get('count', 0),
                'revenue': float(payment_day.get('revenue') or 0),
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
        recent_payments = [
            {
                'id': payment.id,
                'customer_name': payment.customer_name,
                'plan': payment.plan.name,
                'amount': float(payment.amount),
                'status': payment.status,
                'created_at': payment.created_at,
            }
            for payment in PaymentTransaction.objects.select_related('plan')[:5]
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
                'premium_users': request.user.__class__.objects.filter(
                    is_premium=True,
                ).count(),
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
                'payments': PaymentTransaction.objects.count(),
                'active_subscriptions': UserSubscription.objects.filter(
                    is_active=True,
                ).count(),
                'revenue': float(
                    PaymentTransaction.objects.filter(
                        status=PaymentTransaction.STATUS_COMPLETED,
                    ).aggregate(total=Sum('amount'))['total'] or 0
                ),
                'average_mock_score': round(float(average_score or 0), 2),
            },
            'users_by_plan': [
                {
                    'name': 'Premium',
                    'value': request.user.__class__.objects.filter(
                        is_premium=True,
                    ).count(),
                },
                {
                    'name': 'Free',
                    'value': request.user.__class__.objects.filter(
                        is_premium=False,
                    ).count(),
                },
            ],
            'payment_status': [
                {'status': status_value, 'count': count}
                for status_value, count in payment_statuses.items()
            ],
            'timeline': timeline,
            'questions_by_semester': questions_by_semester,
            'mock_attempts_by_subject': mock_attempts_by_subject,
            'recent_payments': recent_payments,
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


class AdminQuestionListView(APIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Question.objects.select_related(
            'year',
            'year__subject',
            'year__subject__semester',
        ).order_by('year__subject__semester__id', 'year__subject__name', '-year__year', 'order', 'id')

    def serialize_question(self, question):
        return {
            'id': question.id,
            'question_text': question.question_text,
            'answer_text': question.answer_text,
            'marks': question.marks,
            'order': question.order,
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

        for field in ['question_text', 'answer_text', 'marks']:
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
            (key or '').strip().lower(): (value or '').strip()
            for key, value in row.items()
        }

        for key in keys:
            value = normalized.get(key)
            if value:
                return value

        return ''

    def resolve_subject(self, row, default_subject_id, default_semester_id):
        subject_id = self.get_value(row, 'subject_id')
        subject_slug = self.get_value(row, 'subject_slug', 'slug')
        subject_name = self.get_value(row, 'subject', 'subject_name')

        if subject_id:
            return Subject.objects.get(pk=subject_id)

        if subject_slug:
            return Subject.objects.get(slug=subject_slug)

        if subject_name:
            subjects = Subject.objects.filter(name__iexact=subject_name)

            if default_semester_id:
                subjects = subjects.filter(semester_id=default_semester_id)

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
        semester_name = self.get_value(row, 'semester')

        if semester_id:
            return Semester.objects.get(pk=semester_id)

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

            if image_paths:
                answer_markdown = (
                    f"{answer_markdown}\n\nImages: {image_paths}"
                    if answer_markdown
                    else f"Images: {image_paths}"
                )

            answers[question_id] = answer_markdown

        return answers

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
            question_id = self.get_value(row, 'question_id')
            question_text = self.get_value(row, 'question_text', 'question')
            answer_text = (
                self.get_value(row, 'answer_text', 'answer', 'answer_markdown')
                or answers_by_question_id.get(question_id, '')
            )
            year_value = self.get_value(row, 'year') or default_year
            marks = self.get_value(row, 'marks')
            order_value = self.get_value(row, 'order')
            question_number = self.get_value(row, 'question_number')
            section_title = self.get_value(row, 'section')
            exam_time = self.get_value(row, 'exam_time')
            instructions = self.get_value(row, 'instructions')

            if not question_text:
                errors.append({'row': index, 'error': 'Question text is required.'})
                continue

            if not year_value:
                errors.append({'row': index, 'error': 'Year is required.'})
                continue

            try:
                subject = self.resolve_or_create_subject(
                    row,
                    default_subject_id,
                    default_semester_id,
                )
            except Subject.DoesNotExist:
                errors.append({'row': index, 'error': 'Subject was not found.'})
                continue
            except ValueError as exc:
                errors.append({'row': index, 'error': str(exc)})
                continue

            try:
                order = int(order_value or question_number or 0)
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

            question = Question.objects.create(
                year=year,
                section=section,
                question_text=question_text,
                answer_text=answer_text,
                marks=marks,
                order=order,
            )
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


class AdminUserListView(APIView):
    permission_classes = [IsAdminUser]

    def serialize_user(self, user):
        return {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'is_premium': user.is_premium,
            'premium_expires_at': user.premium_expires_at,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
            'current_plan': user.current_plan.name if user.current_plan else '',
        }

    def get(self, request):
        users = request.user.__class__.objects.select_related('current_plan').order_by('-date_joined')
        return Response([self.serialize_user(user) for user in users[:250]])


class AdminUserDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        user = get_object_or_404(request.user.__class__, pk=pk)

        for field in ['is_staff', 'is_premium']:
            if field in request.data:
                setattr(user, field, bool(request.data.get(field)))

        premium_expires_at = request.data.get('premium_expires_at')
        if premium_expires_at == '':
            user.premium_expires_at = None

        user.save(update_fields=['is_staff', 'is_premium', 'premium_expires_at'])
        return Response(AdminUserListView().serialize_user(user))


class AdminPaymentListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        payments = PaymentTransaction.objects.select_related('user', 'plan').order_by('-created_at')[:250]
        return Response([
            {
                'id': payment.id,
                'username': payment.user.username,
                'plan': payment.plan.name,
                'amount': float(payment.amount),
                'status': payment.status,
                'payment_method': payment.payment_method,
                'pidx': payment.pidx,
                'purchase_order_id': payment.purchase_order_id,
                'customer_name': payment.customer_name,
                'customer_email': payment.customer_email,
                'customer_phone': payment.customer_phone,
                'created_at': payment.created_at,
                'completed_at': payment.completed_at,
            }
            for payment in payments
        ])


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


class AdminNotificationListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        notifications = Notification.objects.select_related('user').order_by('-created_at')[:250]
        return Response([
            {
                'id': notification.id,
                'username': notification.user.username,
                'type': notification.type,
                'message': notification.message,
                'link_path': notification.link_path,
                'is_read': notification.is_read,
                'created_at': notification.created_at,
            }
            for notification in notifications
        ])


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

    def delete(self, request, pk):
        question = get_object_or_404(MockTestQuestion, pk=pk)
        question.delete()
        return Response(status=204)
