from django.shortcuts import redirect
from django.urls import reverse

class AdminRedirectMiddleware:
    """
    Middleware to redirect staff and admin users away from the default Django /admin/ 
    and onto the custom admin dashboard.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Requirement 1 & 3: Ensure no custom middleware intercepts /admin/* routes.
        # Skip redirect logic when request.path starts with /admin/.
        if not request.path.startswith('/admin/'):
            # Custom dashboard redirect logic for non-admin entry points would go here.
            # Currently, redirection is handled surgically in the login view.
            pass
        
        return self.get_response(request)
