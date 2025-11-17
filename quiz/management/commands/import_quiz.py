from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import json
from quiz.models import Quiz, Question, Answer

class Command(BaseCommand):
    help = "Import a quiz from a JSON file"

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str, help="Path to quiz JSON")

    def handle(self, *args, **options):
        path = options["json_path"]
        try:
            # use utf-8-sig so files with BOM are accepted
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            raise CommandError(f"Failed to read JSON: {e}")

        if "title" not in data or "questions" not in data or not isinstance(data["questions"], list):
            raise CommandError("JSON must include 'title' and a list 'questions'.")

        title = (data.get("title") or "").strip()
        description = (data.get("description") or "").strip()
        time_limit = int(data.get("time_limit_minutes") or 0)
        tags = data.get("tags") if isinstance(data.get("tags"), list) else []

        try:
            with transaction.atomic():
                quiz, created = Quiz.objects.get_or_create(
                    title=title,
                    defaults={"description": description, "time_limit_minutes": time_limit},
                )
                if not created:
                    quiz.description = description
                    quiz.time_limit_minutes = time_limit
                    quiz.save()
                    # remove existing questions to replace on re-import
                    quiz.questions.all().delete()

                for q_index, q in enumerate(data["questions"], start=1):
                    qtext = (q.get("text") or "").strip()
                    if not qtext:
                        raise CommandError(f"Question #{q_index} missing text.")
                    options = q.get("options") or []
                    if not isinstance(options, list) or len(options) < 2:
                        raise CommandError(f"Question #{q_index} must have at least 2 options.")
                    correct_count = sum(1 for o in options if o.get("is_correct") is True)
                    if correct_count != 1:
                        raise CommandError(f"Question #{q_index} must have exactly one correct option (found {correct_count}).")

                    explanation = (q.get("explanation") or "").strip()
                    difficulty = (q.get("difficulty") or "medium").strip().lower()
                    if difficulty not in ("easy", "medium", "hard"):
                        difficulty = "medium"

                    question = Question.objects.create(
                        quiz=quiz,
                        question_text=qtext,
                        explanation=explanation,
                        difficulty=difficulty,
                        order=q_index
                    )
                    answers = []
                    for o in options:
                        a_text = (o.get("text") or "").strip()
                        answers.append(Answer(question=question, text=a_text, is_correct=bool(o.get("is_correct"))))
                    Answer.objects.bulk_create(answers)
        except Exception as e:
            raise CommandError(f"Import failed: {e}")

        self.stdout.write(self.style.SUCCESS(f"Imported quiz: {title}"))
