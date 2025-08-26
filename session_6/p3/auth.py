from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt
from models import User

def role_required(*allowed_roles):
    """
    Decorator to require one of the allowed roles.
    Usage: @role_required('admin') or @role_required('admin', 'editor')
    """
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            # ensure token present and valid
            verify_jwt_in_request()
            claims = get_jwt()
            role = claims.get("role")
            if role not in allowed_roles:
                return jsonify({"msg": "Forbidden: insufficient role"}), 403
            return fn(*args, **kwargs)
        return decorator
    return wrapper
