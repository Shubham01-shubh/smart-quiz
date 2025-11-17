# quiz/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify

class Quiz(models.Model):
    title = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    # temporarily allow nulls and don't enforce unique in DB
    slug = models.SlugField(max_length=255, unique=True)

    class Meta:
        verbose_name_plural = "Quizzes"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # auto-generate slug from title when missing
        if not self.slug:
            base = slugify(self.title)[:180] or "quiz"
            slug = base
            counter = 1
            while Quiz.objects.filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Question(models.Model):
    DIFFICULTY_CHOICES = (("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard"))

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_text = models.TextField()
    explanation = models.TextField(blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default="medium")
    order = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.question_text[:60]


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        prefix = "✔️ " if self.is_correct else ""
        return f"{prefix}{self.text[:60]}"


class QuizAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attempts")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    score = models.IntegerField(default=0)
    date_completed = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(default=600)  # seconds

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title} ({self.score})"


class UserAnswer(models.Model):
    quiz_attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answer = models.ForeignKey(Answer, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('quiz_attempt', 'question')

    def __str__(self):
        return f"{self.quiz_attempt.user.username} - Q:{self.question.id} - A:{self.selected_answer.id}"
