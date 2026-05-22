from rest_framework import serializers
from .models import (
    Semester,
    Subject,
    Syllabus,
    Note,
    Year,
    Discussion,
    DiscussionReply,
    MockTest,
    MockTestAnswer,
    MockTestQuestion,
    MockTestResult,
    Question,
    AnswerContribution,
    QuestionPaper,
    QuestionSection,
    SyllabusSection,
    SyllabusUnit,
)


class SyllabusUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyllabusUnit
        fields = ['id', 'title', 'slug', 'duration', 'content', 'order']


class SyllabusSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyllabusSection
        fields = ['id', 'title', 'content', 'order']


class SyllabusSerializer(serializers.ModelSerializer):
    units = SyllabusUnitSerializer(many=True, read_only=True)
    sections = SyllabusSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Syllabus
        fields = [
            'id',
            'pdf_file',
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
            'units',
            'sections',
            'updated_at',
        ]


class SubjectSerializer(serializers.ModelSerializer):
    syllabus = SyllabusSerializer(read_only=True)

    class Meta:
        model = Subject
        fields = ['id', 'name', 'slug', 'semester', 'syllabus']


class NoteSerializer(serializers.ModelSerializer):
    unit_slug = serializers.CharField(source='unit.slug', read_only=True)
    unit_title = serializers.CharField(source='unit.title', read_only=True)
    unit_order = serializers.IntegerField(source='unit.order', read_only=True)
    unit_duration = serializers.CharField(source='unit.duration', read_only=True)
    unit_content = serializers.CharField(source='unit.content', read_only=True)

    class Meta:
        model = Note
        fields = [
            'id',
            'title',
            'slug',
            'body',
            'pdf_file',
            'unit',
            'unit_slug',
            'unit_title',
            'unit_order',
            'unit_duration',
            'unit_content',
            'credit_name',
            'credit_url',
            'credit_image',
            'order',
            'updated_at',
        ]


class SemesterSerializer(serializers.ModelSerializer):
    subjects = SubjectSerializer(many=True, read_only=True)

    class Meta:
        model = Semester
        fields = ['id', 'name', 'slug', 'subjects']


class YearSerializer(serializers.ModelSerializer):
    class Meta:
        model = Year
        fields = [
            'id',
            'year',
            'institution',
            'institute',
            'level',
            'course_code',
            'full_marks',
            'pass_marks',
            'time',
            'instructions',
        ]


class QuestionSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionSection
        fields = ['id', 'title', 'instruction', 'order']


class QuestionSerializer(serializers.ModelSerializer):
    section = QuestionSectionSerializer(read_only=True)
    approved_contributions = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id',
            'section',
            'question_text',
            'answer_text',
            'marks',
            'order',
            'approved_contributions',
        ]

    def get_approved_contributions(self, obj):
        contributions = getattr(obj, 'approved_contributions_cache', None)
        if contributions is None:
            contributions = obj.contributions.filter(
                status=AnswerContribution.STATUS_APPROVED,
            ).select_related('user')
        return ApprovedAnswerContributionSerializer(contributions, many=True).data


class ApprovedAnswerContributionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AnswerContribution
        fields = ['id', 'username', 'answer_text', 'image', 'created_at']


class AnswerContributionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AnswerContribution
        fields = ['id', 'username', 'answer_text', 'image', 'status', 'created_at']

class QuestionPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionPaper
        fields = ['id', 'pdf_file']


class DiscussionReplySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    child_replies = serializers.SerializerMethodField()

    class Meta:
        model = DiscussionReply
        fields = ['id', 'username', 'body', 'parent', 'child_replies', 'created_at']
        read_only_fields = ['username', 'created_at']

    def get_child_replies(self, obj):
        children = obj.child_replies.all()
        return DiscussionReplySerializer(children, many=True).data


class DiscussionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    replies = serializers.SerializerMethodField()
    reply_count = serializers.IntegerField(source='replies.count', read_only=True)

    class Meta:
        model = Discussion
        fields = ['id', 'username', 'title', 'body', 'reply_count', 'replies', 'created_at']
        read_only_fields = ['username', 'created_at']

    def get_replies(self, obj):
        top_level = obj.replies.filter(parent=None)
        return DiscussionReplySerializer(top_level, many=True).data


class PlatformDiscussionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    reply_count = serializers.IntegerField(source='replies.count', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_slug = serializers.CharField(source='subject.slug', read_only=True)
    semester_name = serializers.CharField(source='subject.semester.name', read_only=True)
    semester_slug = serializers.CharField(source='subject.semester.slug', read_only=True)

    class Meta:
        model = Discussion
        fields = [
            'id',
            'username',
            'title',
            'body',
            'reply_count',
            'created_at',
            'subject_name',
            'subject_slug',
            'semester_name',
            'semester_slug',
        ]


class MockTestQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MockTestQuestion
        fields = [
            'id',
            'question_text',
            'option_a',
            'option_b',
            'option_c',
            'option_d',
            'marks',
        ]


class MockTestSerializer(serializers.ModelSerializer):
    questions = MockTestQuestionSerializer(many=True, read_only=True)
    question_count = serializers.IntegerField(source='questions.count', read_only=True)

    class Meta:
        model = MockTest
        fields = [
            'id',
            'title',
            'duration_minutes',
            'total_marks',
            'question_count',
            'questions',
        ]


class MockTestListSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(source='questions.count', read_only=True)

    class Meta:
        model = MockTest
        fields = ['id', 'title', 'duration_minutes', 'total_marks', 'question_count']


class MockTestResultSerializer(serializers.ModelSerializer):
    mock_test_title = serializers.CharField(source='mock_test.title', read_only=True)

    class Meta:
        model = MockTestResult
        fields = ['id', 'mock_test', 'mock_test_title', 'score', 'total_marks', 'completed_at']


class MockTestAnswerReviewSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    option_a = serializers.CharField(source='question.option_a', read_only=True)
    option_b = serializers.CharField(source='question.option_b', read_only=True)
    option_c = serializers.CharField(source='question.option_c', read_only=True)
    option_d = serializers.CharField(source='question.option_d', read_only=True)
    marks = serializers.IntegerField(source='question.marks', read_only=True)

    class Meta:
        model = MockTestAnswer
        fields = [
            'id',
            'question',
            'question_text',
            'option_a',
            'option_b',
            'option_c',
            'option_d',
            'marks',
            'selected_option',
            'correct_option',
            'is_correct',
        ]
