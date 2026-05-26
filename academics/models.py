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
    pdf_file = models.FileField(upload_to='syllabus/', blank=True)
    course_title = models.CharField(max_length=200, blank=True)
    course_no = models.CharField(max_length=40, blank=True)
    semester_label = models.CharField(max_length=40, blank=True)
    nature = models.CharField(max_length=120, blank=True)
    full_marks = models.CharField(max_length=80, blank=True)
    pass_marks = models.CharField(max_length=80, blank=True)
    credit_hours = models.CharField(max_length=40, blank=True)
    course_description = models.TextField(blank=True)
    course_objective = models.TextField(blank=True)
    laboratory_work = models.TextField(blank=True)
    text_books = models.TextField(blank=True)
    reference_books = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Syllabus - {self.subject.name}"


class SyllabusUnit(models.Model):
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name='units')
    title = models.CharField(max_length=180)
    slug = models.SlugField(blank=True)
    duration = models.CharField(max_length=40, blank=True)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        unique_together = ('syllabus', 'slug')

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.syllabus.subject.name} - {self.title}"


class SyllabusSection(models.Model):
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=160)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.syllabus.subject.name} - {self.title}"


class Note(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='notes')
    unit = models.ForeignKey(
        SyllabusUnit,
        on_delete=models.SET_NULL,
        related_name='notes',
        blank=True,
        null=True,
    )
    title = models.CharField(max_length=220)
    slug = models.SlugField(blank=True)
    body = models.TextField(blank=True)
    pdf_file = models.FileField(upload_to='notes/', blank=True, null=True)
    credit_name = models.CharField(max_length=120, blank=True)
    credit_designation = models.CharField(max_length=160, blank=True)
    credit_url = models.URLField(blank=True)
    credit_image = models.ImageField(upload_to='notes/credits/', blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['unit__order', 'order', 'title']
        unique_together = ('subject', 'slug')

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject.name} - {self.title}"


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
    source_question_id = models.CharField(max_length=40, blank=True, db_index=True)
    source_url = models.URLField(blank=True)
    answer_source_url = models.URLField(blank=True)
    answer_image_paths = models.TextField(blank=True)
    question_text = models.TextField()
    answer_text = models.TextField()
    marks = models.CharField(max_length=20, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['section__order', 'order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['source_question_id'],
                condition=~models.Q(source_question_id=''),
                name='unique_question_source_question_id',
            ),
        ]

    def __str__(self):
        return f"{self.year.subject.name} ({self.year.year}) - {self.question_text[:50]}"


class AnswerContribution(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='contributions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='answer_contributions',
    )
    answer_text = models.TextField()
    image = models.ImageField(
        upload_to='answer_contributions/',
        blank=True,
        null=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='reviewed_answer_contributions',
        blank=True,
        null=True,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.question_id} - {self.status}"


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


class MockTestAnswer(models.Model):
    result = models.ForeignKey(
        MockTestResult,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    question = models.ForeignKey(
        MockTestQuestion,
        on_delete=models.CASCADE,
        related_name='submitted_answers',
    )
    selected_option = models.CharField(max_length=1, blank=True)
    correct_option = models.CharField(max_length=1)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = ('result', 'question')

    def __str__(self):
        return f"{self.result} - {self.question_id} - {self.selected_option or 'unanswered'}"


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
