"""Outbound-URL guard: dangerous schemes are refused, http(s) allowed, private-host opt-in works."""
from aec_api.net import validate_outbound_url


def run():
    # http/https to a public host pass (no DNS needed for the scheme/host checks with allow_private).
    validate_outbound_url("https://hooks.example.com/x", label="t")
    validate_outbound_url("http://hooks.example.com/x", label="t")

    # dangerous / non-http schemes are refused — the concrete local-file/SSRF vector.
    for bad in ("file:///etc/passwd", "gopher://x/y", "ftp://h/f", "data:text/plain,hi", "  file://x"):
        try:
            validate_outbound_url(bad, label="t")
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected reject for scheme: {bad!r}")

    # missing host is refused.
    try:
        validate_outbound_url("https://", label="t")
    except ValueError:
        pass
    else:
        raise AssertionError("expected reject for empty host")

    # require_https refuses plain http.
    try:
        validate_outbound_url("http://h/x", require_https=True, label="t")
    except ValueError:
        pass
    else:
        raise AssertionError("expected reject for http when require_https")

    # allow_private=False refuses a loopback host (resolves locally, no network).
    try:
        validate_outbound_url("http://127.0.0.1/x", allow_private=False, label="t")
    except ValueError:
        pass
    else:
        raise AssertionError("expected reject for loopback when allow_private=False")

    print("NET OK - schemes gated (file/gopher/ftp/data refused), host required, https + private opt-in enforced")


if __name__ == "__main__":
    run()
