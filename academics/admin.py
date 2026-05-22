from django.contrib import admin
from .models import (
    Discussion,
    DiscussionReply,
    MockTest,
    MockTestQuestion,
    MockTestResult,
    Note,
    AnswerContribution,
    Semester,
    Subject,
    Syllabus,
    SyllabusSection,
    SyllabusUnit,
    Year,
    Question,
    QuestionPaper,
    QuestionSection,
)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}  # ✅ Auto fill slug from name


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'semester', 'slug']
    ordering = ['semester', 'name']
    prepopulated_fields = {'slug': ('name',)}  # ✅ Auto fill slug from name


class SyllabusUnitInline(admin.TabularInline):
    model = SyllabusUnit
    extra = 0
    fields = ['title', 'slug', 'duration', 'content', 'order']
    prepopulated_fields = {'slug': ('title',)}


class SyllabusSectionInline(admin.TabularInline):
    model = SyllabusSection
    extra = 0
    fields = ['title', 'content', 'order']


@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ['subject', 'updated_at']
    inlines = [SyllabusUnitInline, SyllabusSectionInline]
    fieldsets = (
        (None, {
            'fields': ('subject', 'pdf_file')
        }),
        ('Course header', {
            'fields': (
                'course_title',
                'course_no',
                'semester_label',
                'nature',
                'full_marks',
                'pass_marks',
                'credit_hours',
            )
        }),
        ('Course details', {
            'fields': (
                'course_description',
                'course_objective',
                'laboratory_work',
                'text_books',
                'reference_books',
            )
        }),
    )


@admin.register(SyllabusUnit)
class SyllabusUnitAdmin(admin.ModelAdmin):
    list_display = ['title', 'syllabus', 'duration', 'order']
    list_filter = ['syllabus__subject__semester', 'syllabus__subject']
    prepopulated_fields = {'slug': ('title',)}
    ordering = ['syllabus', 'order']


@admin.register(SyllabusSection)
class SyllabusSectionAdmin(admin.ModelAdmin):
    list_display = ['title', 'syllabus', 'order']
    list_filter = ['syllabus__subject__semester', 'syllabus__subject']
    search_fields = ['title', 'content', 'syllabus__subject__name']
    ordering = ['syllabus', 'order']


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'unit', 'pdf_file', 'credit_name', 'is_published', 'order', 'updated_at']
    list_filter = ['is_published', 'subject__semester', 'subject']
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ['title', 'body', 'subject__name']
    ordering = ['subject', 'unit__order', 'order', 'title']


class QuestionSectionInline(admin.TabularInline):
    model = QuestionSection
    extra = 0
    fields = ['title', 'instruction', 'order']


@admin.register(Year)
class YearAdmin(admin.ModelAdmin):
    list_display = ['subject', 'year', 'full_marks', 'pass_marks', 'time']
    list_filter = ['subject__semester', 'subject']
    ordering = ['subject', '-year']
    fieldsets = (
        (None, {
            'fields': ('subject', 'year')
        }),
        ('Paper header', {
            'fields': (
                'institution',
                'institute',
                'level',
                'course_code',
                'full_marks',
                'pass_marks',
                'time',
                'instructions',
            )
        }),
    )
    inlines = [QuestionSectionInline]


@admin.register(QuestionSection)
class QuestionSectionAdmin(admin.ModelAdmin):
    list_display = ['title', 'year', 'order', 'instruction']
    list_filter = ['year__subject__semester', 'year__subject', 'year']
    ordering = ['year', 'order']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['get_subject', 'get_year', 'section', 'order', 'marks', 'question_text']
    list_filter = ['year__subject__semester', 'year__subject', 'year', 'section']
    ordering = ['year', 'section__order', 'order']
    fields = ['year', 'section', 'order', 'marks', 'question_text', 'answer_text']

    def get_subject(self, obj):
        return obj.year.subject.name
    get_subject.short_description = 'Subject'

    def get_year(self, obj):
        return obj.year.year
    get_year.short_description = 'Year'


@admin.register(AnswerContribution)
class AnswerContributionAdmin(admin.ModelAdmin):
    list_display = [
        'question',
        'user',
        'image',
        'status',
        'reviewed_by',
        'created_at',
        'reviewed_at',
    ]
    list_filter = ['status', 'question__year__subject__semester', 'question__year__subject']
    search_fields = ['answer_text', 'user__username', 'question__question_text']
    readonly_fields = ['created_at', 'updated_at', 'reviewed_at']


@admin.register(QuestionPaper)
class QuestionPaperAdmin(admin.ModelAdmin):
    list_display = ['get_subject', 'get_year', 'pdf_file']

    def get_subject(self, obj):
        return obj.year.subject.name
    get_subject.short_description = 'Subject'

    def get_year(self, obj):
        return obj.year.year
    get_year.short_description = 'Year'


class MockTestQuestionInline(admin.TabularInline):
    model = MockTestQuestion
    extra = 0


@admin.register(MockTest)
class MockTestAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'duration_minutes', 'total_marks', 'is_active']
    list_filter = ['is_active', 'subject__semester', 'subject']
    search_fields = ['title', 'subject__name']
    inlines = [MockTestQuestionInline]


@admin.register(MockTestQuestion)
class MockTestQuestionAdmin(admin.ModelAdmin):
    list_display = ['mock_test', 'question_text', 'correct_option', 'marks']
    list_filter = ['mock_test__subject']
    search_fields = ['question_text', 'mock_test__title']


@admin.register(MockTestResult)
class MockTestResultAdmin(admin.ModelAdmin):
    list_display = ['user', 'mock_test', 'score', 'total_marks', 'completed_at']
    list_filter = ['mock_test__subject']
    search_fields = ['user__username', 'mock_test__title']
    date_hierarchy = 'completed_at'


class DiscussionReplyInline(admin.TabularInline):
    model = DiscussionReply
    extra = 0
    fields = ['user', 'body', 'parent', 'created_at']
    readonly_fields = ['created_at']


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'user', 'created_at']
    list_filter = ['subject__semester', 'subject']
    search_fields = ['title', 'body', 'user__username']
    date_hierarchy = 'created_at'
    inlines = [DiscussionReplyInline]


@admin.register(DiscussionReply)
class DiscussionReplyAdmin(admin.ModelAdmin):
    list_display = ['discussion', 'user', 'parent', 'created_at']
    search_fields = ['discussion__title', 'body', 'user__username']
    date_hierarchy = 'created_at'
