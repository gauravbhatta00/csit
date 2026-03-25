from django.db import models
from django.utils.text import slugify


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

    class Meta:
        unique_together = ('subject', 'year')
        ordering = ['-year']

    def __str__(self):
        return f"{self.subject.name} - {self.year}"


class Question(models.Model):
    year = models.ForeignKey(Year, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    answer_text = models.TextField()

    def __str__(self):
        return f"{self.year.subject.name} ({self.year.year}) - {self.question_text[:50]}"


class QuestionPaper(models.Model):
    year = models.OneToOneField(Year, on_delete=models.CASCADE, related_name='paper')
    pdf_file = models.FileField(upload_to='question_papers/')

    def __str__(self):
        return f"{self.year.subject.name} - {self.year.year}"