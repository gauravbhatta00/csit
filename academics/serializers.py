from rest_framework import serializers
from .models import (
    Semester,
    Subject,
    Syllabus,
    Note,
    CreditPerson,
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


class SyllabusSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Syllabus
        fields = ['id', 'pdf_file', 'course_title', 'course_no', 'updated_at']


class SubjectSerializer(serializers.ModelSerializer):
    syllabus = SyllabusSerializer(read_only=True)
    year_count = serializers.IntegerField(read_only=True, default=0)
    question_count = serializers.IntegerField(read_only=True, default=0)
    mock_test_count = serializers.IntegerField(read_only=True, default=0)
    discussion_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Subject
        fields = [
            'id',
            'name',
            'slug',
            'semester',
            'syllabus',
            'year_count',
            'question_count',
            'mock_test_count',
            'discussion_count',
        ]


class SubjectListSerializer(serializers.ModelSerializer):
    syllabus = SyllabusSummarySerializer(read_only=True)
    year_count = serializers.IntegerField(read_only=True, default=0)
    question_count = serializers.IntegerField(read_only=True, default=0)
    mock_test_count = serializers.IntegerField(read_only=True, default=0)
    discussion_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Subject
        fields = [
            'id',
            'name',
            'slug',
            'semester',
            'syllabus',
            'year_count',
            'question_count',
            'mock_test_count',
            'discussion_count',
        ]


class CreditPersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditPerson
        fields = [
            'id',
            'name',
            'designation',
            'link_url',
            'image',
            'image_url',
            'portfolio_url',
        ]


class NoteSerializer(serializers.ModelSerializer):
    unit_slug = serializers.CharField(source='unit.slug', read_only=True)
    unit_title = serializers.CharField(source='unit.title', read_only=True)
    unit_order = serializers.IntegerField(source='unit.order', read_only=True)
    unit_duration = serializers.CharField(source='unit.duration', read_only=True)
    unit_content = serializers.CharField(source='unit.content', read_only=True)
    credit_person = CreditPersonSerializer(read_only=True)
    credit = serializers.SerializerMethodField()

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
            'credit_person',
            'credit',
            'credit_name',
            'credit_designation',
            'credit_url',
            'credit_image',
            'order',
            'updated_at',
        ]

    def get_credit(self, obj):
        if obj.credit_person_id:
            return CreditPersonSerializer(obj.credit_person, context=self.context).data

        if not any([obj.credit_name, obj.credit_designation, obj.credit_url, obj.credit_image]):
            return None

        image_url = None
        if obj.credit_image:
            try:
                image_url = obj.credit_image.url
            except ValueError:
                image_url = None

        return {
            'id': None,
            'name': obj.credit_name,
            'designation': obj.credit_designation,
            'link_url': obj.credit_url,
            'image': image_url,
            'image_url': '',
            'portfolio_url': '',
        }


class SemesterSerializer(serializers.ModelSerializer):
    subjects = SubjectSerializer(many=True, read_only=True)

    class Meta:
        model = Semester
        fields = ['id', 'name', 'slug', 'subjects']


class SemesterListSerializer(serializers.ModelSerializer):
    subjects = SubjectListSerializer(many=True, read_only=True)

    class Meta:
        model = Semester
        fields = ['id', 'name', 'slug', 'subjects']


class YearSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(read_only=True, default=0)

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
            'question_count',
        ]


class QuestionSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionSection
        fields = ['id', 'title', 'instruction', 'order']


class QuestionSerializer(serializers.ModelSerializer):
    section = QuestionSectionSerializer(read_only=True)
    approved_contributions = serializers.SerializerMethodField()
    answer_source_url = serializers.SerializerMethodField()
    answer_image_paths = serializers.SerializerMethodField()
    answer_text = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id',
            'section',
            'source_question_id',
            'source_url',
            'answer_source_url',
            'answer_image_paths',
            'question_text',
            'answer_text',
            'marks',
            'order',
            'approved_contributions',
        ]

    def get_approved_contributions(self, obj):
        if not self.can_view_answers():
            return []
        contributions = getattr(obj, 'approved_contributions_cache', None)
        if contributions is None:
            contributions = obj.contributions.filter(
                status=AnswerContribution.STATUS_APPROVED,
                is_main_answer=False,
            ).select_related('user')
        return ApprovedAnswerContributionSerializer(contributions, many=True).data

    def get_answer_source_url(self, obj):
        return obj.answer_source_url if self.can_view_answers() else ''

    def get_answer_image_paths(self, obj):
        return obj.answer_image_paths if self.can_view_answers() else ''

    def get_answer_text(self, obj):
        return obj.answer_text if self.can_view_answers() else ''

    def can_view_answers(self):
        request = self.context.get('request')
        return bool(request and request.user and request.user.is_authenticated)


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
