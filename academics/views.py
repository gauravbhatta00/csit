from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Semester, Subject, Syllabus, Year, Question, QuestionPaper
from .serializers import (
    SemesterSerializer, SubjectSerializer,
    SyllabusSerializer, YearSerializer,
    QuestionSerializer, QuestionPaperSerializer
)
from accounts.permissions import IsPremiumUser, IsSingleDeviceAuthenticated


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