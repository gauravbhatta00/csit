from rest_framework import serializers
from .models import Semester, Subject, Syllabus, Year, Question, QuestionPaper, Discussion, DiscussionReply,MockTestQuestion,MockTestResult,MockTest


class SyllabusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Syllabus
        fields = ['id', 'pdf_file', 'updated_at']


class SubjectSerializer(serializers.ModelSerializer):
    syllabus = SyllabusSerializer(read_only=True)  # ✅ Syllabus nested inside subject

    class Meta:
        model = Subject
        fields = ['id', 'name', 'semester', 'syllabus']


class SemesterSerializer(serializers.ModelSerializer):
    subjects = SubjectSerializer(many=True, read_only=True)  # ✅ Subjects nested inside semester

    class Meta:
        model = Semester
        fields = ['id', 'name', 'subjects']


class YearSerializer(serializers.ModelSerializer):
    class Meta:
        model = Year
        fields = ['id', 'year']


class QuestionSerializer(serializers.ModelSerializer):
    answer_text = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ['id', 'question_text', 'answer_text']

    def get_answer_text(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                if request.user.profile.is_premium:
                    return obj.answer_text
            except Exception:
                pass
        return "🔒 Upgrade to premium to see the answer."


class QuestionPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionPaper
        fields = ['id', 'pdf_file']

class DiscussionReplySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    # ✅ Recursive — replies to replies
    child_replies = serializers.SerializerMethodField()

    class Meta:
        model = DiscussionReply
        fields = ['id', 'username', 'body', 'parent', 'child_replies', 'created_at']
        read_only_fields = ['username', 'created_at']

    def get_child_replies(self, obj):
        # ✅ Get all replies to this reply
        children = obj.child_replies.all()
        return DiscussionReplySerializer(children, many=True).data


class DiscussionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    # ✅ Only top level replies (parent=None)
    replies = serializers.SerializerMethodField()
    reply_count = serializers.IntegerField(source='replies.count', read_only=True)

    class Meta:
        model = Discussion
        fields = ['id', 'username', 'title', 'body', 'reply_count', 'replies', 'created_at']
        read_only_fields = ['username', 'created_at']

    def get_replies(self, obj):
        # ✅ Only get top level replies
        top_level = obj.replies.filter(parent=None)
        return DiscussionReplySerializer(top_level, many=True).data
class MockTestQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MockTestQuestion
        # ✅ Never expose correct_option to frontend
        fields = ['id', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'marks']


class MockTestSerializer(serializers.ModelSerializer):
    questions = MockTestQuestionSerializer(many=True, read_only=True)
    question_count = serializers.IntegerField(source='questions.count', read_only=True)

    class Meta:
        model = MockTest
        fields = ['id', 'title', 'duration_minutes', 'total_marks', 'question_count', 'questions']


# ✅ List serializer — no questions (for listing multiple tests)
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