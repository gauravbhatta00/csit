from rest_framework import serializers
from .models import Semester, Subject, Syllabus, Year, Question, QuestionPaper


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