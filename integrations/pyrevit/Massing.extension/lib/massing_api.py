# -*- coding: utf-8 -*-
"""Massing REST client for the pyRevit bridge — std-lib only (works on pyRevit's IronPython 2.7
*and* CPython 3 engines; no `requests` dependency). Talks to a Massing API with an AEC_API_KEY
bearer token: find/create a project, upload the model's IFC, kick + poll the Fragments publish,
and round-trip BCF issues. The HTTP transport is injectable so the flow is unit-testable.

Author: Massing (massing.build) — free, open Revit -> Massing bridge (no paid APS bridge needed).
"""
import json
import time
import uuid

try:                                   # CPython 3 (pyRevit 4.8+/5)
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except ImportError:                    # IronPython 2.7 (legacy pyRevit)
    from urllib2 import Request, urlopen, HTTPError, URLError  # type: ignore


class MassingError(Exception):
    pass


def _b(s):
    return s if isinstance(s, bytes) else s.encode("utf-8")


def build_multipart(field, filename, data):
    """Encode a single-file multipart/form-data body. Returns (content_type, body_bytes)."""
    boundary = "----massing" + uuid.uuid4().hex
    crlf = b"\r\n"
    body = crlf.join([
        _b("--" + boundary),
        _b('Content-Disposition: form-data; name="%s"; filename="%s"' % (field, filename)),
        b"Content-Type: application/octet-stream",
        b"",
        _b(data),
        _b("--" + boundary + "--"),
        b"",
    ])
    return "multipart/form-data; boundary=" + boundary, body


class MassingClient(object):
    """Thin Massing API client. `app_url` is the web viewer origin (for deep links); defaults to
    `base_url` when not given. `transport(method, url, headers, body) -> (status, bytes)` is
    overridable for tests."""

    def __init__(self, base_url, api_key, app_url=None, transport=None, timeout=120):
        if not base_url:
            raise MassingError("Massing API URL is not set — configure it in the Massing > Settings button.")
        self.base = base_url.rstrip("/")
        self.app_url = (app_url or base_url).rstrip("/")
        self.key = api_key or ""
        self.timeout = timeout
        self._transport = transport or self._http

    # --- transport ---------------------------------------------------------
    def _headers(self, extra=None):
        h = {}
        if self.key:
            h["Authorization"] = "Bearer " + self.key
        if extra:
            h.update(extra)
        return h

    def _http(self, method, url, headers, body):
        req = Request(url, data=body, headers=headers or {})
        req.get_method = lambda: method
        try:
            resp = urlopen(req, timeout=self.timeout)
            return resp.getcode(), resp.read()
        except HTTPError as e:
            return e.code, e.read()
        except URLError as e:
            raise MassingError("cannot reach Massing at %s (%s)" % (self.base, e))

    def _json(self, method, path, payload=None):
        headers = self._headers()
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = _b(json.dumps(payload))
        status, raw = self._transport(method, self.base + path, headers, body)
        if status >= 400:
            raise MassingError("%s %s -> HTTP %s: %s" % (method, path, status, raw[:200]))
        return json.loads(raw.decode("utf-8") or "{}") if raw else {}

    # --- projects ----------------------------------------------------------
    def list_projects(self):
        return self._json("GET", "/projects")

    def create_project(self, name):
        return self._json("POST", "/projects", {"name": name})["id"]

    def find_or_create_project(self, name):
        """Reuse an existing project of the same name (so re-publishing updates it) else create one."""
        for p in self.list_projects() or []:
            if p.get("name") == name:
                return p["id"]
        return self.create_project(name)

    # --- model upload + publish -------------------------------------------
    def upload_ifc(self, pid, ifc_bytes, filename="source.ifc", publish=True):
        ctype, body = build_multipart("file", filename, ifc_bytes)
        headers = self._headers({"Content-Type": ctype})
        url = "%s/projects/%s/source-ifc?publish=%s" % (self.base, pid, "true" if publish else "false")
        status, raw = self._transport("POST", url, headers, body)
        if status >= 400:
            raise MassingError("IFC upload -> HTTP %s: %s" % (status, raw[:200]))
        return json.loads(raw.decode("utf-8") or "{}")

    def publish_status(self, pid):
        return self._json("GET", "/projects/%s/publish/status" % pid)

    def wait_for_publish(self, pid, timeout=300, interval=3, sleeper=None):
        sleeper = sleeper or time.sleep
        waited = 0
        while waited < timeout:
            s = self.publish_status(pid)
            state = s.get("state")
            if state in ("done", "idle"):
                return s
            if state == "error":
                raise MassingError("publish failed: %s" % s.get("detail"))
            sleeper(interval)
            waited += interval
        raise MassingError("publish timed out after %ss" % timeout)

    # --- BCF round-trip ----------------------------------------------------
    def bcf_export(self, pid):
        """Download the project's issues as a .bcfzip (bytes)."""
        status, raw = self._transport("GET", "%s/projects/%s/bcf/export" % (self.base, pid),
                                      self._headers(), None)
        if status >= 400:
            raise MassingError("BCF export -> HTTP %s" % status)
        return raw

    def bcf_import(self, pid, bcf_bytes, filename="issues.bcfzip"):
        ctype, body = build_multipart("file", filename, bcf_bytes)
        headers = self._headers({"Content-Type": ctype})
        status, raw = self._transport("POST", "%s/projects/%s/bcf/import" % (self.base, pid), headers, body)
        if status >= 400:
            raise MassingError("BCF import -> HTTP %s: %s" % (status, raw[:200]))
        return json.loads(raw.decode("utf-8") or "{}") if raw else {}

    # --- deep links --------------------------------------------------------
    def viewer_url(self, pid):
        return "%s/?project=%s" % (self.app_url, pid)
