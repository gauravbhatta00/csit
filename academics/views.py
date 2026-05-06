from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Semester, Subject, Syllabus, Year, Question, QuestionPaper,MockTest, MockTestQuestion, MockTestResult,Discussion, DiscussionReply
from .serializers import (
    SemesterSerializer, SubjectSerializer,
    SyllabusSerializer, YearSerializer,
    QuestionSerializer, QuestionPaperSerializer,
    MockTestSerializer, MockTestListSerializer, MockTestResultSerializer,
    DiscussionSerializer, DiscussionReplySerializer 
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
        )

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
    """List all mock tests for a subject — no questions included."""
    permission_classes = [AllowAny]
    serializer_class = MockTestListSerializer   # ✅ Uses list serializer

    def get_queryset(self):
        return MockTest.objects.filter(
            subject__slug=self.kwargs['subject_slug'],
            is_active=True
        )


class MockTestDetailView(RetrieveAPIView):
    """Get specific mock test with all questions."""
    permission_classes = [AllowAny]
    serializer_class = MockTestSerializer       # ✅ Full serializer with questions

    def get_object(self):
        return MockTest.objects.get(id=self.kwargs['pk'])


class SubmitMockTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            mock_test = MockTest.objects.get(id=pk)
        except MockTest.DoesNotExist:
            return Response({'error': 'Test not found.'}, status=404)

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
            total_marks=mock_test.total_marks
        )

        return Response({
            'score': score,
            'total_marks': mock_test.total_marks,
            'percentage': round((score / mock_test.total_marks) * 100, 2),
            'result_id': result.id
        })


class UserMockTestResultListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MockTestResultSerializer

    def get_queryset(self):
        return MockTestResult.objects.filter(
            user=self.request.user
        ).order_by('-completed_at')
    

class MockTestResultDetailView(APIView):
    """Get result by result_id."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # ✅ pk is now result_id not mock_test_id
        try:
            result = MockTestResult.objects.get(
                id=pk,
                user=request.user  # ✅ User can only see their own results
            )
        except MockTestResult.DoesNotExist:
            return Response(
                {'error': 'Result not found.'},
                status=404
            )

        return Response({
            'result_id': result.id,
            'mock_test_id': result.mock_test.id,
            'mock_test_title': result.mock_test.title,
            'subject': result.mock_test.subject.name,
            'score': result.score,
            'total_marks': result.total_marks,
            'percentage': round((result.score / result.total_marks) * 100, 2),
            'completed_at': result.completed_at
        })
class SubjectDiscussionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, subject_slug):
        try:
            subject = Subject.objects.get(slug=subject_slug)
        except Subject.DoesNotExist:
            return Response({'error': 'Subject not found.'}, status=404)

        discussions = Discussion.objects.filter(subject=subject)
        serializer = DiscussionSerializer(discussions, many=True)
        return Response(serializer.data)

    def post(self, request, subject_slug):
        try:
            subject = Subject.objects.get(slug=subject_slug)
        except Subject.DoesNotExist:
            return Response({'error': 'Subject not found.'}, status=404)

        serializer = DiscussionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user, subject=subject)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class DiscussionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            discussion = Discussion.objects.get(id=pk)
        except Discussion.DoesNotExist:
            return Response({'error': 'Discussion not found.'}, status=404)

        serializer = DiscussionSerializer(discussion)
        return Response(serializer.data)

    def delete(self, request, pk):
        try:
            discussion = Discussion.objects.get(id=pk, user=request.user)
            discussion.delete()
            return Response({'message': 'Discussion deleted.'})
        except Discussion.DoesNotExist:
            return Response({'error': 'Not found or not authorized.'}, status=404)


class DiscussionReplyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        """
        Add reply to discussion or reply to a reply.
        Send parent_id in body to reply to a specific reply.
        """
        try:
            discussion = Discussion.objects.get(id=pk)
        except Discussion.DoesNotExist:
            return Response({'error': 'Discussion not found.'}, status=404)

        body = request.data.get('body')
        parent_id = request.data.get('parent_id', None)  # ✅ Optional parent reply

        if not body:
            return Response({'error': 'Body is required.'}, status=400)

        parent = None
        if parent_id:
            try:
                parent = DiscussionReply.objects.get(id=parent_id, discussion=discussion)
            except DiscussionReply.DoesNotExist:
                return Response({'error': 'Parent reply not found.'}, status=404)

        reply = DiscussionReply.objects.create(
            discussion=discussion,
            user=request.user,
            body=body,
            parent=parent  # ✅ None = top level, set = nested reply
        )

        serializer = DiscussionReplySerializer(reply)
        return Response(serializer.data, status=201)

    def delete(self, request, pk):
        try:
            reply = DiscussionReply.objects.get(id=pk, user=request.user)
            reply.delete()
            return Response({'message': 'Reply deleted.'})
        except DiscussionReply.DoesNotExist:
            return Response({'error': 'Not found or not authorized.'}, status=404)
class SearchView(APIView):
    """Search across subjects and questions."""
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get('q', '')

        if not query:
            return Response({'error': 'Search query required.'}, status=400)

        # ✅ Search subjects
        subjects = Subject.objects.filter(
            name__icontains=query
        ).select_related('semester')

        # ✅ Search questions
        questions = Question.objects.filter(
            question_text__icontains=query
        ).select_related('year__subject')

        return Response({
            'subjects': SubjectSerializer(subjects, many=True).data,
            'questions': [
                {
                    'id': q.id,
                    'question_text': q.question_text,
                    'subject': q.year.subject.name,
                    'year': q.year.year,
                    'subject_slug': q.year.subject.slug,
                }
                for q in questions
            ]
        })
    




class DiscussionReplyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            discussion = Discussion.objects.get(id=pk)
        except Discussion.DoesNotExist:
            return Response({'error': 'Discussion not found.'}, status=404)

        body = request.data.get('body')
        parent_id = request.data.get('parent_id', None)

        if not body:
            return Response({'error': 'Body is required.'}, status=400)

        parent = None
        if parent_id:
            try:
                parent = DiscussionReply.objects.get(id=parent_id, discussion=discussion)
            except DiscussionReply.DoesNotExist:
                return Response({'error': 'Parent reply not found.'}, status=404)

        reply = DiscussionReply.objects.create(
            discussion=discussion,
            user=request.user,
            body=body,
            parent=parent
        )

        # ✅ Notify discussion owner (not if replying to own discussion)
        if discussion.user != request.user:
            notify_reply(
                discussion_owner=discussion.user,
                replier_username=request.user.username,
                discussion_title=discussion.title
            )

        # ✅ Notify parent reply owner if nested reply
        if parent and parent.user != request.user:
            notify_reply(
                discussion_owner=parent.user,
                replier_username=request.user.username,
                discussion_title=discussion.title
            )

        serializer = DiscussionReplySerializer(reply)
        return Response(serializer.data, status=201)