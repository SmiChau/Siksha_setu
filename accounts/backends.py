from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class EmailBackend(ModelBackend):
    """
    Custom authentication backend that authenticates using email
    and ensures the user is verified before allowing login.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user using email and password.
        Only allow login if user is verified (is_verified=True) and active (is_active=True).
        """
        if username is None:
            username = kwargs.get('email')
        
        if username is None or password is None:
            return None
        
        try:
            user = User.objects.get(email=username)
        except User.DoesNotExist:
            # Run the default password hasher to prevent timing attacks
            User().set_password(password)
            return None
        
        # Check if user is verified
        if not user.is_verified:
            return None
        
        # Check if user is active
        if not user.is_active:
            return None
        
        # Check password
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None

