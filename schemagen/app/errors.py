"""Every non-2xx answer is {"error": {code, message, retry}} (docs/api.md): a plain sentence for the user, the full
cause (traceback, stderr) in the log file. No handler ever lets an exception reach the server as a bare 500."""
from __future__ import annotations

import traceback
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import userdata

STATUS = {"no-project": 409, "bad-request": 400, "not-found": 404, "import-failed": 422, "graphviz-missing": 503, "render-failed": 500,
          "sim-failed": 500, "internal": 500}
INTERNAL = "Something went wrong. The details are in the log file; please try again."


class AppError(Exception):
    def __init__(self, code: str, message: str, retry: bool = False, detail: str = ""):
        super().__init__(message)
        self.code, self.message, self.retry, self.detail = code, message, retry, detail


def body(code: str, message: str, retry: bool = False) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "retry": retry}}, status_code=STATUS.get(code, 500))


def convert(e: BaseException, where: str = "") -> AppError:
    """Any exception as an AppError; the cause goes to the log."""
    from ..importers.records import ModelError
    from ..renderers.wireviz import RenderError
    lg = userdata.log()
    if isinstance(e, AppError):
        if e.detail: lg.warning("%s %s: %s\n%s", where, e.code, e.message, e.detail)
        return e
    if isinstance(e, RenderError):
        lg.warning("%s %s: %s\n%s", where, e.code, e.message, e.detail)
        return AppError(e.code, e.message, retry=e.code == "render-failed")
    if isinstance(e, ModelError):
        lg.warning("%s project input problems:\n%s", where, e)
        ps = e.problems
        return AppError("import-failed", f"The project could not be read: {ps[0]}" + (f" (and {len(ps) - 1} more problems)" if len(ps) > 1 else ""))
    if isinstance(e, SystemExit):
        lg.warning("%s %s", where, e)
        return AppError("bad-request", str(e.code if e.code is not None else e).splitlines()[0][:300] or "The request could not be done.")
    lg.error("%s unexpected error\n%s", where, "".join(traceback.format_exception(type(e), e, e.__traceback__)))
    return AppError("internal", INTERNAL, retry=True)


class Route(APIRoute):
    """Runs the endpoint and turns whatever it raises (SystemExit too) into an AppError."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        h = super().get_route_handler()

        async def run(request: Request) -> Any:
            try: return await h(request)
            except (HTTPException, StarletteHTTPException, RequestValidationError): raise
            except BaseException as e:  # noqa: BLE001
                if isinstance(e, (KeyboardInterrupt, GeneratorExit)): raise
                raise convert(e, f"{request.method} {request.url.path}") from None
        return run


def install(app: FastAPI) -> None:
    app.router.route_class = Route

    @app.exception_handler(AppError)
    async def app_error(request: Request, e: AppError) -> JSONResponse:
        return body(e.code, e.message, e.retry)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, e: StarletteHTTPException) -> JSONResponse:
        code = {404: "not-found", 405: "bad-request", 400: "bad-request", 409: "no-project"}.get(e.status_code, "bad-request" if e.status_code < 500 else "internal")
        msg = "Not found." if e.status_code == 404 and e.detail in (None, "", "Not Found") else str(e.detail or "The request could not be done.")
        return body(code, msg[:1].upper() + msg[1:])

    @app.exception_handler(RequestValidationError)
    async def bad_body(request: Request, e: RequestValidationError) -> JSONResponse:
        errs = e.errors()
        where = ".".join(str(x) for x in errs[0].get("loc", ())[1:]) if errs else ""
        return body("bad-request", f"The request is not valid{f' ({where})' if where else ''}: {errs[0].get('msg', '') if errs else ''}".rstrip(": "))

    @app.exception_handler(Exception)
    async def anything(request: Request, e: Exception) -> JSONResponse:
        a = convert(e, f"{request.method} {request.url.path}")
        return body(a.code, a.message, a.retry)
