from django.urls import path
from .views import (
    SemesterListView,
    SemesterSubjectListView,
    SubjectSyllabusView,
    SubjectYearListView,
    YearQuestionListView,
    YearQuestionPaperView,
    SubjectMockTestListView,
    MockTestDetailView,
    SubmitMockTestView, 
    UserMockTestResultListView,
    MockTestResultDetailView,
    SearchView, 
    DiscussionReplyView,
    DiscussionDetailView,
    SubjectDiscussionListView,
)

urlpatterns = [
    # ✅ Semesters
    path('semesters/', SemesterListView.as_view()),
    path('semesters/<slug:semester_slug>/subjects/', SemesterSubjectListView.as_view()),

    # ✅ Syllabus
    path('subjects/<slug:subject_slug>/syllabus/', SubjectSyllabusView.as_view()),

    # ✅ Years
    path('subjects/<slug:subject_slug>/years/', SubjectYearListView.as_view()),

    # ✅ Questions
    path('subjects/<slug:subject_slug>/questions/<str:year>/', YearQuestionListView.as_view()),

    # ✅ Question Papers (premium)
    path('subjects/<slug:subject_slug>/papers/<str:year>/', YearQuestionPaperView.as_view()),
    path('subjects/<slug:subject_slug>/mock-tests/', SubjectMockTestListView.as_view()),
    path('mock-tests/<int:pk>/', MockTestDetailView.as_view()),
    path('mock-tests/<int:pk>/submit/', SubmitMockTestView.as_view()),
    path('mock-tests/results/', UserMockTestResultListView.as_view()),
    path('mock-tests/results/<int:pk>/', MockTestResultDetailView.as_view()),
    path('search/', SearchView.as_view()),
    path('subjects/<slug:subject_slug>/discussions/', SubjectDiscussionListView.as_view()),
    path('discussions/<int:pk>/', DiscussionDetailView.as_view()),                           # GET + DELETE
    path('discussions/<int:pk>/reply/', DiscussionReplyView.as_view()),
]