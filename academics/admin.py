from django.contrib import admin
from .models import Semester, Subject, Syllabus, Year, Question, QuestionPaper


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}  # ✅ Auto fill slug from name


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'semester', 'slug']
    ordering = ['semester', 'name']
    prepopulated_fields = {'slug': ('name',)}  # ✅ Auto fill slug from name


@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ['subject', 'updated_at']


@admin.register(Year)
class YearAdmin(admin.ModelAdmin):
    list_display = ['subject', 'year']
    ordering = ['subject', '-year']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['get_subject', 'get_year', 'question_text']

    def get_subject(self, obj):
        return obj.year.subject.name
    get_subject.short_description = 'Subject'

    def get_year(self, obj):
        return obj.year.year
    get_year.short_description = 'Year'


@admin.register(QuestionPaper)
class QuestionPaperAdmin(admin.ModelAdmin):
    list_display = ['get_subject', 'get_year', 'pdf_file']

    def get_subject(self, obj):
        return obj.year.subject.name
    get_subject.short_description = 'Subject'

    def get_year(self, obj):
        return obj.year.year
    get_year.short_description = 'Year'