from django.urls import path
from .views import (
    SemesterListView,
    SemesterSubjectListView,
    SubjectSyllabusView,
    SubjectYearListView,
    YearQuestionListView,
    YearQuestionPaperView,
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
]