from functools import wraps

from datasette import Forbidden
from datasette_plugin_router import Router

router = Router()

CA460_ACCESS_NAME = "ca460_access"


def check_permission():
    """Decorator for routes requiring CA 460 access."""

    def decorator(func):
        @wraps(func)
        async def wrapper(datasette, request, **kwargs):
            result = await datasette.allowed(
                action=CA460_ACCESS_NAME, actor=request.actor
            )
            if not result:
                raise Forbidden("Permission denied for CA 460 access")
            return await func(datasette=datasette, request=request, **kwargs)

        return wrapper

    return decorator
