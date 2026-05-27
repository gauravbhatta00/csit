from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from PIL import Image, UnidentifiedImageError
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from .models import (
    Discussion,
    DiscussionReply,
    AnswerContribution,
    MockTest,
    MockTestAnswer,
    MockTestResult,
    Note,
    Semester,
    Subject,
    Syllabus,
    Year,
    Question,
    QuestionPaper,
)
from .serializers import (
    DiscussionReplySerializer,
    DiscussionSerializer,
    AnswerContributionSerializer,
    MockTestAnswerReviewSerializer,
    MockTestListSerializer,
    MockTestResultSerializer,
    MockTestSerializer,
    PlatformDiscussionSerializer,
    SemesterListSerializer,
    SemesterSerializer,
    SubjectListSerializer,
    SubjectSerializer,
    SyllabusSerializer, YearSerializer,
    QuestionSerializer, QuestionPaperSerializer,
    NoteSerializer,
)
from accounts.permissions import IsSingleDeviceAuthenticated
from .utils import notify_reply


def build_slug_or_id_query(value, slug_field='slug', id_field='id'):
    query = Q(**{slug_field: value})
    if str(value).isdigit():
        query |= Q(**{id_field: int(value)})
    return query


def get_subject_by_slug_or_id(value):
    return get_object_or_404(Subject, build_slug_or_id_query(value))


def parse_mock_test_question_ids(request_data):
    selected_ids = (
        request_data.get('question_ids')
        or request_data.get('attempt_question_ids')
        or request_data.get('selected_question_ids')
        or []
    )
    if isinstance(selected_ids, str):
        selected_ids = [
            value.strip()
            for value in selected_ids.split(',')
            if value.strip()
        ]
    return {str(question_id) for question_id in selected_ids}


class SemesterListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = SemesterListSerializer

    def get_queryset(self):
        subjects = Subject.objects.select_related('syllabus').annotate(
            year_count=Count('years', distinct=True),
            question_count=Count('years__questions', distinct=True),
            mock_test_count=Count('mock_tests', distinct=True),
            discussion_count=Count('discussions', distinct=True),
        )
        return Semester.objects.prefetch_related(
            Prefetch('subjects', queryset=subjects),
        )


class SemesterSubjectListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubjectListSerializer

    def get_queryset(self):
        # ✅ Filter by slug instead of pk
        semester_value = self.kwargs['semester_slug']
        query = Q(semester__slug=semester_value)
        if str(semester_value).isdigit():
            query |= Q(semester_id=int(semester_value))
        return Subject.objects.filter(query).select_related('syllabus').annotate(
            year_count=Count('years', distinct=True),
            question_count=Count('years__questions', distinct=True),
            mock_test_count=Count('mock_tests', distinct=True),
            discussion_count=Count('discussions', distinct=True),
        )


class SubjectSyllabusView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = SyllabusSerializer

    def get_object(self):
        # ✅ Filter by subject slug
        subject = get_subject_by_slug_or_id(self.kwargs['subject_slug'])
        return get_object_or_404(
            Syllabus.objects.prefetch_related('units', 'sections'),
            subject=subject,
        )


class SubjectDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubjectSerializer

    def get_object(self):
        return get_object_or_404(
            Subject.objects.select_related('semester', 'syllabus').prefetch_related(
                'syllabus__units',
                'syllabus__sections',
            ),
            build_slug_or_id_query(self.kwargs['subject_slug']),
        )


class SubjectYearListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = YearSerializer

    def get_queryset(self):
        subject = get_subject_by_slug_or_id(self.kwargs['subject_slug'])
        return Year.objects.filter(subject=subject).annotate(
            question_count=Count('questions', distinct=True),
        )


class SubjectNoteListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NoteSerializer

    def get_queryset(self):
        subject = get_subject_by_slug_or_id(self.kwargs['subject_slug'])
        queryset = Note.objects.filter(
            subject=subject,
            is_published=True,
        ).select_related('unit')
        unit_slug = (self.request.query_params.get('unit') or '').strip()
        if unit_slug:
            queryset = queryset.filter(unit__slug=unit_slug)
        return queryset


class SubjectNoteDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = NoteSerializer

    def get_object(self):
        subject = get_subject_by_slug_or_id(self.kwargs['subject_slug'])
        return get_object_or_404(
            Note.objects.select_related('unit'),
            subject=subject,
            slug=self.kwargs['note_slug'],
            is_published=True,
        )


class YearQuestionListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = QuestionSerializer

    def get_queryset(self):
        subject = get_subject_by_slug_or_id(self.kwargs['subject_slug'])
        return Question.objects.filter(
            year__subject=subject,
            year__year=self.kwargs['year']
        ).select_related('section').prefetch_related(
            Prefetch(
                'contributions',
                queryset=AnswerContribution.objects.filter(
                    status=AnswerContribution.STATUS_APPROVED,
                    is_main_answer=False,
                ).select_related('user'),
                to_attr='approved_contributions_cache',
            )
        )

    def get_serializer_context(self):
        return {'request': self.request}


class YearQuestionPaperView(RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsSingleDeviceAuthenticated]
    serializer_class = QuestionPaperSerializer

    def get_object(self):
        subject = get_subject_by_slug_or_id(self.kwargs['subject_slug'])
        return QuestionPaper.objects.get(
            year__subject=subject,
            year__year=self.kwargs['year']
        )


class QuestionContributionListView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_question(self, pk):
        return get_object_or_404(Question, pk=pk)

    def get(self, request, pk):
        question = self.get_question(pk)
        contributions = question.contributions.filter(
            status=AnswerContribution.STATUS_APPROVED,
            is_main_answer=False,
        ).select_related('user')
        return Response(AnswerContributionSerializer(contributions, many=True).data)

    def post(self, request, pk):
        question = self.get_question(pk)
        answer_text = (request.data.get('answer_text') or '').strip()
        image = request.FILES.get('image')

        if not answer_text and not image:
            return Response(
                {'detail': 'Answer text or image is required.'},
                status=400,
            )

        if image:
            try:
                Image.open(image).verify()
                image.seek(0)
            except (OSError, UnidentifiedImageError):
                return Response({'detail': 'Upload a valid image file.'}, status=400)

        contribution = AnswerContribution.objects.create(
            question=question,
            user=request.user,
            answer_text=answer_text,
            image=image,
        )
        return Response(
            AnswerContributionSerializer(contribution).data,
            status=201,
        )


class SubjectMockTestListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = MockTestListSerializer

    def get_queryset(self):
        subject = get_subject_by_slug_or_id(self.kwargs['subject_slug'])
        return MockTest.objects.filter(
            subject=subject,
            is_active=True,
        )


class MockTestDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = MockTestSerializer

    def get_object(self):
        return MockTest.objects.get(id=self.kwargs['pk'])


class SubmitMockTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            mock_test = MockTest.objects.prefetch_related('questions').get(id=pk)
        except MockTest.DoesNotExist:
            return Response({'detail': 'Test not found.'}, status=404)

        answers = request.data.get('answers', {})
        if not isinstance(answers, dict):
            return Response({'detail': 'Answers must be an object.'}, status=400)

        question_id_values = parse_mock_test_question_ids(request.data) or set(answers.keys())
        try:
            question_ids = {int(question_id) for question_id in question_id_values}
        except (TypeError, ValueError):
            return Response({'detail': 'Question IDs must be integers.'}, status=400)

        score = 0
        question_queryset = mock_test.questions.all()
        if question_ids:
            question_queryset = question_queryset.filter(id__in=question_ids)
        questions = list(question_queryset)

        if question_ids and len(questions) != len(question_ids):
            return Response(
                {'detail': 'One or more submitted questions do not belong to this test.'},
                status=400,
            )

        total_marks = sum(question.marks for question in questions)

        for question in questions:
            submitted = (answers.get(str(question.id)) or '').upper()
            if submitted and submitted.upper() == question.correct_option:
                score += question.marks

        result = MockTestResult.objects.create(
            user=request.user,
            mock_test=mock_test,
            score=score,
            total_marks=total_marks,
        )

        MockTestAnswer.objects.bulk_create([
            MockTestAnswer(
                result=result,
                question=question,
                selected_option=(answers.get(str(question.id)) or '').upper(),
                correct_option=question.correct_option,
                is_correct=(
                    (answers.get(str(question.id)) or '').upper()
                    == question.correct_option
                ),
            )
            for question in questions
        ])

        return Response({
            'score': score,
            'total_marks': total_marks,
            'percentage': round((score / total_marks) * 100, 2)
            if total_marks else 0,
            'result_id': result.id,
        })


class UserMockTestResultListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MockTestResultSerializer

    def get_queryset(self):
        return MockTestResult.objects.filter(user=self.request.user)


class MockTestResultDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            result = MockTestResult.objects.select_related(
                'mock_test',
                'mock_test__subject',
            ).get(id=pk, user=request.user)
        except MockTestResult.DoesNotExist:
            return Response({'detail': 'Result not found.'}, status=404)

        return Response({
            'result_id': result.id,
            'mock_test_id': result.mock_test.id,
            'mock_test_title': result.mock_test.title,
            'subject': result.mock_test.subject.name,
            'score': result.score,
            'total_marks': result.total_marks,
            'percentage': round((result.score / result.total_marks) * 100, 2)
            if result.total_marks else 0,
            'completed_at': result.completed_at,
            'answers': MockTestAnswerReviewSerializer(
                result.answers.select_related('question'),
                many=True,
            ).data,
        })


class SubjectDiscussionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, subject_slug):
        subject = get_subject_by_slug_or_id(subject_slug)

        discussions = Discussion.objects.filter(subject=subject).select_related('user')
        serializer = DiscussionSerializer(discussions, many=True)
        return Response(serializer.data)

    def post(self, request, subject_slug):
        subject = get_subject_by_slug_or_id(subject_slug)

        serializer = DiscussionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, subject=subject)
        return Response(serializer.data, status=201)


class PlatformDiscussionListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 8))
        except (TypeError, ValueError):
            limit = 8

        limit = max(1, min(limit, 24))
        randomize = request.query_params.get('random') in {'1', 'true', 'yes'}
        ordering = '?' if randomize else '-created_at'
        discussions = (
            Discussion.objects.select_related('user', 'subject', 'subject__semester')
            .prefetch_related('replies')
            .order_by(ordering)[:limit]
        )

        serializer = PlatformDiscussionSerializer(discussions, many=True)
        return Response(serializer.data)


class DiscussionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            discussion = Discussion.objects.get(id=pk)
        except Discussion.DoesNotExist:
            return Response({'detail': 'Discussion not found.'}, status=404)

        return Response(DiscussionSerializer(discussion).data)

    def delete(self, request, pk):
        try:
            discussion = Discussion.objects.get(id=pk, user=request.user)
        except Discussion.DoesNotExist:
            return Response({'detail': 'Not found or not authorized.'}, status=404)

        discussion.delete()
        return Response({'message': 'Discussion deleted.'})


class DiscussionReplyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            discussion = Discussion.objects.get(id=pk)
        except Discussion.DoesNotExist:
            return Response({'detail': 'Discussion not found.'}, status=404)

        body = request.data.get('body')
        parent_id = request.data.get('parent_id')

        if not body:
            return Response({'detail': 'Body is required.'}, status=400)

        parent = None
        if parent_id:
            try:
                parent = DiscussionReply.objects.get(
                    id=parent_id,
                    discussion=discussion,
                )
            except DiscussionReply.DoesNotExist:
                return Response({'detail': 'Parent reply not found.'}, status=404)

        reply = DiscussionReply.objects.create(
            discussion=discussion,
            user=request.user,
            body=body,
            parent=parent,
        )

        if discussion.user != request.user:
            notify_reply(
                discussion_owner=discussion.user,
                replier_username=request.user.username,
                discussion=discussion,
            )

        if parent and parent.user != request.user:
            notify_reply(
                discussion_owner=parent.user,
                replier_username=request.user.username,
                discussion=discussion,
            )

        return Response(DiscussionReplySerializer(reply).data, status=201)

    def delete(self, request, pk):
        try:
            reply = DiscussionReply.objects.get(id=pk, user=request.user)
        except DiscussionReply.DoesNotExist:
            return Response({'detail': 'Not found or not authorized.'}, status=404)

        reply.delete()
        return Response({'message': 'Reply deleted.'})


class SearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get('q', '')

        if not query:
            return Response({'detail': 'Search query required.'}, status=400)

        subjects = Subject.objects.filter(name__icontains=query).select_related('semester')
        questions = Question.objects.filter(
            question_text__icontains=query,
        ).select_related('year__subject')

        return Response({
            'subjects': [
                {
                    'id': subject.id,
                    'name': subject.name,
                    'slug': subject.slug,
                    'semester': subject.semester.id,
                    'semester_name': subject.semester.name,
                    'semester_slug': subject.semester.slug,
                }
                for subject in subjects
            ],
            'questions': [
                {
                    'id': question.id,
                    'question_text': question.question_text,
                    'subject': question.year.subject.name,
                    'year': question.year.year,
                    'subject_slug': question.year.subject.slug,
                    'semester_slug': question.year.subject.semester.slug,
                }
                for question in questions
            ],
        })
