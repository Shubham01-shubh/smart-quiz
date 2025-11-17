from django.contrib import admin
from .models import Quiz, Question, Answer, QuizAttempt, UserAnswer

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 4
    fields = ('text', 'is_correct')
    show_change_link = True

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "quiz", "question_text")
    inlines = [AnswerInline]

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    # show only fields that exist on your Quiz model
    list_display = ("id", "title",)   # add other real fields here (e.g. 'description')
    search_fields = ("title",)
    ordering = ("title",)

# register the rest (if not already registered)
admin.site.register(QuizAttempt)
admin.site.register(UserAnswer)
