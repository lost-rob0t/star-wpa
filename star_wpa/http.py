"""HTTP effects never follow redirects, including same-origin redirects."""
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_http(request, *, timeout, direct=False):
    # Authenticated numeric-loopback collection must ignore ambient proxies.
    handlers = [NoRedirect()]
    if direct:
        handlers.append(ProxyHandler({}))
    return build_opener(*handlers).open(request, timeout=timeout)
