from django.urls import path
from . import views
from .views import signup
from .views import import_quiz_view

urlpatterns = [
    path('', views.home, name='home'),
    path('quizzes/', views.quiz_select, name='quiz_select'),
    path('start/<int:quiz_id>/', views.quiz_start, name='quiz_start'),
    path('take/<int:attempt_id>/', views.quiz_take, name='quiz_take'),
    path('submit/<int:attempt_id>/', views.quiz_submit, name='quiz_submit'),
    path('leaderboard/<int:quiz_id>/', views.leaderboard, name='leaderboard'),
    path('history/', views.history, name='history'),
    path('attempt/<int:attempt_id>/', views.attempt_detail, name='attempt_detail'),
    path('signup/', signup, name='signup'),
    path("quiz/import/", import_quiz_view, name="quiz_import"),
    path('certificate/<int:attempt_id>/', views.download_certificate, name='download_certificate'),
]
