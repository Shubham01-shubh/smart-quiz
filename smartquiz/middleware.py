# smartquiz/middleware.py
from django.utils.deprecation import MiddlewareMixin

class NoCacheAuthPages(MiddlewareMixin):
    def process_response(self, request, response):
        # Prevent caching on Accounts (security) AND Quiz pages (cheating/UX)
        if request.path.startswith('/accounts/') or request.path.startswith('/quiz/take/') or request.path.startswith('/attempt/'):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response