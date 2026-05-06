from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import (
    Discussion,
    DiscussionReply,
    MockTest,
    MockTestResult,
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
    MockTestListSerializer,
    MockTestResultSerializer,
    MockTestSerializer,
    SemesterSerializer, SubjectSerializer,
    SyllabusSerializer, YearSerializer,
    QuestionSerializer, QuestionPaperSerializer
)
from accounts.permissions import IsPremiumUser, IsSingleDeviceAuthenticated
from .utils import notify_reply


class SemesterListView(ListAPIView):
    permission_classes = [AllowAny]
    queryset = Semester.objects.prefetch_related('subjects__syllabus')
    serializer_class = SemesterSerializer


class SemesterSubjectListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubjectSerializer

    def get_queryset(self):
        # ✅ Filter by slug instead of pk
        return Subject.objects.filter(
            semester__slug=self.kwargs['semester_slug']
        ).select_related('syllabus')


class SubjectSyllabusView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = SyllabusSerializer

    def get_object(self):
        # ✅ Filter by subject slug
        return Syllabus.objects.get(subject__slug=self.kwargs['subject_slug'])


class SubjectYearListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = YearSerializer

    def get_queryset(self):
        return Year.objects.filter(subject__slug=self.kwargs['subject_slug'])


class YearQuestionListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = QuestionSerializer

    def get_queryset(self):
        return Question.objects.filter(
            year__subject__slug=self.kwargs['subject_slug'],
            year__year=self.kwargs['year']
        ).select_related('section')

    def get_serializer_context(self):
        return {'request': self.request}


class YearQuestionPaperView(RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsPremiumUser, IsSingleDeviceAuthenticated]
    serializer_class = QuestionPaperSerializer

    def get_object(self):
        return QuestionPaper.objects.get(
            year__subject__slug=self.kwargs['subject_slug'],
            year__year=self.kwargs['year']
        )


class SubjectMockTestListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = MockTestListSerializer

    def get_queryset(self):
        return MockTest.objects.filter(
            subject__slug=self.kwargs['subject_slug'],
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
        score = 0

        for question in mock_test.questions.all():
            submitted = answers.get(str(question.id))
            if submitted and submitted.upper() == question.correct_option:
                score += question.marks

        result = MockTestResult.objects.create(
            user=request.user,
            mock_test=mock_test,
            score=score,
            total_marks=mock_test.total_marks,
        )

        return Response({
            'score': score,
            'total_marks': mock_test.total_marks,
            'percentage': round((score / mock_test.total_marks) * 100, 2)
            if mock_test.total_marks else 0,
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
        })


class SubjectDiscussionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, subject_slug):
        try:
            subject = Subject.objects.get(slug=subject_slug)
        except Subject.DoesNotExist:
            return Response({'detail': 'Subject not found.'}, status=404)

        discussions = Discussion.objects.filter(subject=subject).select_related('user')
        serializer = DiscussionSerializer(discussions, many=True)
        return Response(serializer.data)

    def post(self, request, subject_slug):
        try:
            subject = Subject.objects.get(slug=subject_slug)
        except Subject.DoesNotExist:
            return Response({'detail': 'Subject not found.'}, status=404)

        serializer = DiscussionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, subject=subject)
        return Response(serializer.data, status=201)


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
                discussion_title=discussion.title,
            )

        if parent and parent.user != request.user:
            notify_reply(
                discussion_owner=parent.user,
                replier_username=request.user.username,
                discussion_title=discussion.title,
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
            'subjects': SubjectSerializer(subjects, many=True).data,
            'questions': [
                {
                    'id': question.id,
                    'question_text': question.question_text,
                    'subject': question.year.subject.name,
                    'year': question.year.year,
                    'subject_slug': question.year.subject.slug,
                }
                for question in questions
            ],
        })
