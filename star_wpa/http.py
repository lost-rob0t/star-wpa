"""HTTP effects never follow redirects, including same-origin redirects."""
from urllib.request import HTTPRedirectHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_http(request, *, timeout):
    # Retain standard proxy handling and TLS verification.
    return build_opener(NoRedirect()).open(request, timeout=timeout)
