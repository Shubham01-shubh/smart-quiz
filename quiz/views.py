import json
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import Quiz, Question, Answer, QuizAttempt, UserAnswer
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.db import transaction
from django.contrib import messages


@login_required
def home(request):
    latest_attempt = QuizAttempt.objects.filter(user=request.user).order_by('-date_completed').first()
    return render(request, 'quiz/home.html', {'latest_attempt': latest_attempt})


def leaderboard(request, quiz_id):
    top_attempts = QuizAttempt.objects.filter(quiz_id=quiz_id).order_by('-score')[:10]
    return render(request, 'quiz/leaderboard.html', {'top_attempts': top_attempts})


@login_required
def history(request):
    if request.user.is_staff:
        # If user is admin/staff, show all attempts
        attempts = QuizAttempt.objects.all().order_by('-date_completed')
    else:
        # Otherwise, show only their own attempts
        attempts = QuizAttempt.objects.filter(user=request.user).order_by('-date_completed')
    return render(request, 'quiz/history.html', {'attempts': attempts})


@login_required
def attempt_detail(request, attempt_id):
    if request.user.is_staff:
        attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    else:
        attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)

    user_answers = UserAnswer.objects.select_related("question", "selected_answer").filter(quiz_attempt=attempt)

    qa_details = []
    for ua in user_answers:
        q = ua.question
        answers = Answer.objects.filter(question=q)
        qa_details.append({
            'question': q,
            'answers': answers,
            'selected_answer_id': ua.selected_answer.id if ua.selected_answer else None,
        })

    context = {
        'attempt': attempt,
        'qa_details': qa_details,
    }
    return render(request, 'quiz/attempt_detail.html', context)


@login_required
def quiz_start(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    # support both presence/absence of time_limit_minutes field on the model
    time_limit_minutes = getattr(quiz, "time_limit_minutes", None)
    # default to 10 minutes if not set or falsy
    duration_minutes = time_limit_minutes or 10
    try:
        duration = int(duration_minutes) * 60
    except Exception:
        duration = 10 * 60
    attempt = QuizAttempt.objects.create(
        user=request.user, quiz=quiz, started_at=timezone.now(), duration_seconds=duration
    )
    return redirect("quiz_take", attempt_id=attempt.id)


@login_required
def quiz_take(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    # use related_name "questions" (your model declares related_name="questions")
    questions = attempt.quiz.questions.prefetch_related("answers")
    return render(request, "quiz/quiz_take.html", {"attempt": attempt, "questions": questions})


@login_required
def quiz_submit(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    questions = attempt.quiz.questions.all()

    # Optional server-side enforcement of quiz duration
    if attempt.started_at and attempt.duration_seconds:
        elapsed = (timezone.now() - attempt.started_at).total_seconds()
        if elapsed > attempt.duration_seconds + 5:  # small grace period
            return redirect("attempt_detail", attempt_id=attempt.id)

    # Prevent duplicate user answers for same attempt (if user resubmits)
    UserAnswer.objects.filter(quiz_attempt=attempt).delete()

    # Grade and store user answers
    total_correct = 0
    for q in questions:
        selected_id = request.POST.get(f"q_{q.id}")
        if not selected_id:
            continue
        selected = Answer.objects.filter(id=selected_id, question=q).first()
        if not selected:
            continue
        UserAnswer.objects.create(
            quiz_attempt=attempt, question=q, selected_answer=selected
        )
        if selected.is_correct:
            total_correct += 1

    attempt.score = total_correct
    attempt.date_completed = timezone.now()
    attempt.save()
    return redirect("attempt_detail", attempt_id=attempt.id)


def signup(request):
    """
    Simple signup view using Django's UserCreationForm.
    On success, log the user in and redirect to home.
    """
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Log the user in directly after signup
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def quiz_select(request):
    quizzes = Quiz.objects.all().order_by("title")
    return render(request, "quiz/quiz_select.html", {"quizzes": quizzes})


@login_required
def import_quiz_view(request):
    """
    Admin-only JSON importer for quizzes.
    Expects a single uploaded file field named "file" (multipart/form-data).
    JSON shape (top-level): title, description, time_limit_minutes, tags, questions[]
    Each question: text, explanation (optional), difficulty (optional), options[] {text, is_correct}
    """

    if not request.user.is_staff:
        return HttpResponseForbidden("Admins only.")
    if request.method == "GET":
        return render(request, "quiz/import_quiz.html")

    file = request.FILES.get("file")
    if not file:
        return HttpResponseBadRequest("No file uploaded.")

    # load JSON safely (file is Django UploadedFile)
    try:
        # json.load works with file-like objects; but handle BOM/encoding issues
        try:
            data = json.load(file)
        except ValueError:
            # fallback: decode bytes and use json.loads (handles BOM via utf-8-sig)
            raw = file.read()
            if isinstance(raw, bytes):
                text = raw.decode("utf-8-sig")
            else:
                text = str(raw)
            data = json.loads(text)
    except Exception as e:
        return render(request, "quiz/import_quiz.html", {"error": f"Invalid JSON: {e}"})

    # Basic validation
    if "title" not in data or "questions" not in data:
        return render(request, "quiz/import_quiz.html", {"error": "JSON must include 'title' and 'questions'."})
    if not isinstance(data["questions"], list) or not data["questions"]:
        return render(request, "quiz/import_quiz.html", {"error": "'questions' must be a non-empty list."})

    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    # read time_limit but only use if model supports it
    try:
        time_limit = int(data.get("time_limit_minutes") or 0)
    except (TypeError, ValueError):
        time_limit = 0

    # prepare defaults only for fields actually present on the model
    defaults = {"description": description}
    if hasattr(Quiz, "time_limit_minutes"):
        defaults["time_limit_minutes"] = time_limit

    try:
        with transaction.atomic():
            quiz, created = Quiz.objects.get_or_create(
                title=title,
                defaults=defaults,
            )
            if not created:
                # update existing meta safely if field exists
                quiz.description = description
                if hasattr(Quiz, "time_limit_minutes"):
                    quiz.time_limit_minutes = time_limit
                quiz.save()
                # delete existing questions (use the related_name 'questions' used in models)
                if hasattr(quiz, "questions"):
                    quiz.questions.all().delete()
                else:
                    quiz.question_set.all().delete()

            for q_index, q in enumerate(data["questions"], start=1):
                qtext = (q.get("text") or "").strip()
                if not qtext:
                    raise ValueError(f"Question #{q_index} missing text.")
                options = q.get("options") or []
                if not isinstance(options, list) or len(options) < 2:
                    raise ValueError(f"Question #{q_index} must have at least 2 options.")
                correct_count = sum(1 for o in options if o.get("is_correct") is True)
                if correct_count != 1:
                    raise ValueError(f"Question #{q_index} must have exactly one correct option (found {correct_count}).")
                explanation = (q.get("explanation") or "").strip()
                difficulty = (q.get("difficulty") or "medium").strip()

                # Create question using the field name in your model: question_text
                question_kwargs = {"quiz": quiz, "question_text": qtext}
                if hasattr(Question, "explanation"):
                    question_kwargs["explanation"] = explanation
                if hasattr(Question, "difficulty"):
                    question_kwargs["difficulty"] = difficulty

                question = Question.objects.create(**question_kwargs)

                answers = []
                for o in options:
                    a_text = (o.get("text") or "").strip()
                    answers.append(Answer(question=question, text=a_text, is_correct=bool(o.get("is_correct"))))
                Answer.objects.bulk_create(answers)

    except Exception as e:
        return render(request, "quiz/import_quiz.html", {"error": f"Import failed: {e}"})

    messages.success(request, f"Imported quiz: {title}")
    return redirect("quiz_select")
