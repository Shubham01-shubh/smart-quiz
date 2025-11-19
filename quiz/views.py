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
from django.db.models import Count
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.units import inch

@login_required
def home(request):
    # 1. Get the latest attempt for the "Latest Attempt" alert (existing logic)
    latest_attempt = QuizAttempt.objects.filter(user=request.user).order_by('-date_completed').first()
    
    # 2. NEW: Get last 5 attempts for the graph (oldest to newest for the graph flow)
    recent_attempts = QuizAttempt.objects.filter(user=request.user).order_by('-date_completed')[:5]
    # We reverse it in Python so the graph goes Left(Old) -> Right(New)
    recent_attempts = reversed(list(recent_attempts))
    
    # 3. Prepare data lists for Chart.js
    dates = []
    scores = []
    quiz_titles = []
    
    for attempt in recent_attempts:
        # Format date as "Nov 19"
        dates.append(attempt.date_completed.strftime("%b %d"))
        scores.append(attempt.score)
        quiz_titles.append(attempt.quiz.title)

    context = {
        'latest_attempt': latest_attempt,
        'dates': dates,         # Sending these to template
        'scores': scores,       # Sending these to template
        'quiz_titles': quiz_titles,
    }
    return render(request, 'quiz/home.html', context)


def leaderboard(request, quiz_id):
    top_attempts = QuizAttempt.objects.filter(quiz_id=quiz_id).order_by('-score')[:10]
    return render(request, 'quiz/leaderboard.html', {'top_attempts': top_attempts})


@login_required
def history(request):
    # Initialize empty lists for the chart
    chart_usernames = []
    chart_counts = []

    if request.user.is_staff:
        # 1. Get all attempts for the table
        attempts = QuizAttempt.objects.all().select_related('user', 'quiz').order_by('-date_completed')
        
        # 2. NEW: Calculate "Who attempted the most quizzes?"
        # This groups by username, counts the IDs, and orders by biggest count
        user_stats = QuizAttempt.objects.values('user__username') \
            .annotate(total_attempts=Count('id')) \
            .order_by('-total_attempts')[:10] # Top 10 only
        
        # 3. Prepare data for Chart.js
        for stat in user_stats:
            chart_usernames.append(stat['user__username'])
            chart_counts.append(stat['total_attempts'])
            
    else:
        # Standard student view (no changes needed here)
        attempts = QuizAttempt.objects.filter(user=request.user).select_related('quiz').order_by('-date_completed')

    context = {
        'attempts': attempts,
        'chart_usernames': chart_usernames, # Sending to template
        'chart_counts': chart_counts,       # Sending to template
    }
    return render(request, 'quiz/history.html', context)


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

@login_required
def download_certificate(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)

    if attempt.score <= 0:
        return HttpResponse("Score too low for certificate.", status=400)

    # Create the HttpResponse object with the appropriate PDF headers.
    response = HttpResponse(content_type='application/pdf')
    filename = f"Certificate_{attempt.user.username}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Create the PDF object, using the response object as its "file."
    p = canvas.Canvas(response, pagesize=landscape(A4))
    
    # --- SETUP VARIABLES ---
    width, height = landscape(A4)
    center_x = width / 2.0
    
    # --- 1. BACKGROUND & BORDER ---
    # Light Cream Background
    p.setFillColorRGB(0.98, 0.97, 0.95) 
    p.rect(0, 0, width, height, fill=1, stroke=0)
    
    # Fancy Double Border (Navy Blue)
    p.setStrokeColorRGB(0.13, 0.31, 0.63) # #2050a0
    p.setLineWidth(5)
    p.rect(30, 30, width-60, height-60) # Outer Thick
    
    p.setLineWidth(1)
    p.rect(38, 38, width-76, height-76) # Inner Thin

    # Corner Accents (Gold squares)
    p.setFillColorRGB(0.83, 0.69, 0.22) # Gold
    p.rect(30, 30, 10, 10, fill=1, stroke=0) # Bottom Left
    p.rect(width-40, 30, 10, 10, fill=1, stroke=0) # Bottom Right
    p.rect(30, height-40, 10, 10, fill=1, stroke=0) # Top Left
    p.rect(width-40, height-40, 10, 10, fill=1, stroke=0) # Top Right

    # --- 2. HEADER TEXT ---
    # Helper function to center text
    def draw_centered_text(text, y, font, size, color=colors.black):
        p.setFont(font, size)
        p.setFillColor(color)
        text_width = p.stringWidth(text, font, size)
        p.drawString(center_x - (text_width / 2.0), y, text)

    draw_centered_text("CERTIFICATE", height - 140, "Helvetica-Bold", 48, colors.HexColor('#2050a0'))
    draw_centered_text("OF ACHIEVEMENT", height - 170, "Helvetica", 14, colors.gray)
    
    draw_centered_text("This certificate is proudly presented to", height - 230, "Helvetica-Oblique", 14, colors.darkgrey)

    # --- 3. STUDENT NAME (Big & Classy) ---
    name = attempt.user.username
    draw_centered_text(name, height - 290, "Times-BoldItalic", 50, colors.black)
    
    # Underline for name
    p.setLineWidth(1)
    p.setStrokeColor(colors.black)
    p.line(center_x - 150, height - 300, center_x + 150, height - 300)

    # --- 4. DETAILS ---
    quiz_name = attempt.quiz.title
    draw_centered_text(f"For successfully completing the assessment", height - 340, "Helvetica", 14, colors.darkgrey)
    draw_centered_text(quiz_name, height - 370, "Helvetica-Bold", 22, colors.HexColor('#148cb4'))
    
    draw_centered_text(f"Score Achieved: {attempt.score}", height - 400, "Helvetica", 12, colors.black)

    # --- 5. THE BADGE (Programmatic Drawing) ---
    # We draw a Gold Seal visually using circles and a star shape logic
    p.saveState()
    p.translate(width - 100, 100) # Move to bottom right corner
    p.setFillColorRGB(0.83, 0.69, 0.22) # Gold
    p.setStrokeColor(colors.white)
    p.setLineWidth(3)
    
    # Draw the seal circle
    p.circle(0, 0, 40, fill=1, stroke=1)
    p.setLineWidth(1)
    p.circle(0, 0, 32, fill=0, stroke=1) # Inner ring
    
    # Text inside seal
    p.setFont("Helvetica-Bold", 8)
    p.setFillColor(colors.white)
    p.drawCentredString(0, 10, "VERIFIED")
    p.drawCentredString(0, -2, "SUCCESS")
    p.drawCentredString(0, -14, "2025")
    p.restoreState()

    # --- 6. SIGNATURES & DATE ---
    date_str = attempt.date_completed.strftime("%B %d, %Y")
    
    # Date (Bottom Left)
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.black)
    p.drawString(100, 100, f"Date: {date_str}")
    p.line(100, 95, 250, 95) # Line

    # Signature (Bottom Center)
    p.drawString(center_x - 50, 100, "Smart Quiz Admin")
    p.line(center_x - 50, 95, center_x + 100, 95)
    p.setFont("Helvetica-Oblique", 8)
    p.drawString(center_x - 50, 80, "(Authorized Signature)")

    # Close the PDF object cleanly, and we're done.
    p.showPage()
    p.save()
    return response