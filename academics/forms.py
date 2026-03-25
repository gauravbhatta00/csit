from django import forms
from .models import QuestionPaper, Subject

class QuestionPaperAdminForm(forms.ModelForm):
    class Meta:
        model = QuestionPaper
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ Show all subjects with semester context visible in the label
        self.fields['subject'].queryset = Subject.objects.select_related('semester').all()