from functools import wraps

from datasette import Forbidden
from datasette_plugin_router import Router

router = Router()

ACCESS_PERMISSION = "datasette-ca460-access"
INGEST_PERMISSION = "datasette-ca460-ingest"


def check_permission(action: str = ACCESS_PERMISSION):
    """Decorator for routes requiring a CA 460 permission. Defaults to access."""

    def decorator(func):
        @wraps(func)
        async def wrapper(datasette, request, **kwargs):
            result = await datasette.allowed(action=action, actor=request.actor)
            if not result:
                raise Forbidden(f"Permission denied: {action}")
            return await func(datasette=datasette, request=request, **kwargs)

        return wrapper

    return decorator
