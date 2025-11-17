# smartquiz/urls.py (project-level)
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.auth.views import LoginView


# Custom login to hide the navbar on the login page
class SQLogin(LoginView):
    extra_context = {'hide_navbar': True}
    redirect_authenticated_user = True

urlpatterns = [
    path('admin/', admin.site.urls),

    # Optional: avoid /accounts/profile/ 404 if someone lands there
    path('accounts/profile/', lambda r: redirect('home')),

    # Override the default login view BEFORE including auth URLs
    path('accounts/login/', SQLogin.as_view(), name='login'),

    # Built-in auth routes (logout, password reset, etc.)
    path('accounts/', include('django.contrib.auth.urls')),

    # Your app routes
    path('quiz/', include('quiz.urls')),

    # Root -> home
    path('', lambda r: redirect('home')),

 
]
