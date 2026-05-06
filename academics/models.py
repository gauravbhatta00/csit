from django.db import models
from django.utils.text import slugify
from django.conf import settings


class Semester(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True, blank=True)  # ✅ e.g. semester-1

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Subject(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)  # ✅ e.g. operating-system

    def save(self, *args, **kwargs):
        if not self.slug:
            # ✅ Include semester to avoid duplicate slugs across semesters
            self.slug = slugify(f"{self.semester.name}-{self.name}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.semester.name} - {self.name}"


class Syllabus(models.Model):
    subject = models.OneToOneField(Subject, on_delete=models.CASCADE, related_name='syllabus')
    pdf_file = models.FileField(upload_to='syllabus/')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Syllabus - {self.subject.name}"


class Year(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='years')
    year = models.CharField(max_length=10)
    institution = models.CharField(max_length=120, default='Tribhuvan University')
    institute = models.CharField(max_length=160, default='Institute of Science and Technology')
    level = models.CharField(max_length=160, default='Bachelor Level / Science')
    course_code = models.CharField(max_length=40, blank=True)
    full_marks = models.CharField(max_length=40, default='60')
    pass_marks = models.CharField(max_length=40, default='24')
    time = models.CharField(max_length=40, default='3 Hours')
    instructions = models.TextField(
        blank=True,
        default='Candidates are required to give their answers in their own words as far as practicable.\nThe figures in the margin indicate full marks.'
    )

    class Meta:
        unique_together = ('subject', 'year')
        ordering = ['-year']

    def __str__(self):
        return f"{self.subject.name} - {self.year}"


class QuestionSection(models.Model):
    year = models.ForeignKey(Year, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=80)
    instruction = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.year.subject.name} {self.year.year} - {self.title}"


class Question(models.Model):
    year = models.ForeignKey(Year, on_delete=models.CASCADE, related_name='questions')
    section = models.ForeignKey(
        QuestionSection,
        on_delete=models.SET_NULL,
        related_name='questions',
        blank=True,
        null=True
    )
    question_text = models.TextField()
    answer_text = models.TextField()
    marks = models.CharField(max_length=20, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['section__order', 'order', 'id']

    def __str__(self):
        return f"{self.year.subject.name} ({self.year.year}) - {self.question_text[:50]}"


class QuestionPaper(models.Model):
    year = models.OneToOneField(Year, on_delete=models.CASCADE, related_name='paper')
    pdf_file = models.FileField(upload_to='question_papers/')

    def __str__(self):
        return f"{self.year.subject.name} - {self.year.year}"


class MockTest(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='mock_tests')
    title = models.CharField(max_length=200)
    duration_minutes = models.PositiveIntegerField(default=30)
    total_marks = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.subject.name} - {self.title}"


class MockTestQuestion(models.Model):
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=200)
    option_b = models.CharField(max_length=200)
    option_c = models.CharField(max_length=200)
    option_d = models.CharField(max_length=200)
    correct_option = models.CharField(
        max_length=1,
        choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')],
    )
    marks = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.question_text[:50]


class MockTestResult(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='test_results',
    )
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='results')
    score = models.PositiveIntegerField(default=0)
    total_marks = models.PositiveIntegerField()
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-completed_at']

    def __str__(self):
        return f"{self.user.username} - {self.mock_test.title} - {self.score}/{self.total_marks}"


class Discussion(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='discussions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class DiscussionReply(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='child_replies',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.user.username} on {self.discussion.title}"
