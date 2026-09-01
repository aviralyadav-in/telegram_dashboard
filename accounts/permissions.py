from functools import wraps

from django.http import HttpResponseForbidden


def admin_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return HttpResponseForbidden(
                "Login required."
            )

        if not (
            request.user.is_staff
            or request.user.is_superuser
        ):
            return HttpResponseForbidden(
                "Admin access required."
            )

        return view_func(
            request,
            *args,
            **kwargs
        )

    return wrapper