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
        # Only redirect if accessing the default admin and the user is staff/admin
        if request.path.startswith('/admin/') and not request.path.startswith('/adminpanel/'):
            if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'role', '') == 'admin' or request.user.is_superuser):
                # Redirect authenticated staff/admin users to custom dashboard
                # We skip this if they are trying to logout or other specific actions if needed, 
                # but generally we want them in the custom portal.
                return redirect('adminpanel:dashboard')
        
        return self.get_response(request)
