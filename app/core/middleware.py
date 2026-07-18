from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse
from starlette.datastructures import Headers

class LimitUploadSizeMiddleware:
  def __init__(self, app: ASGIApp, max_upload_size: int):
    self.app = app
    self.max_upload_size = max_upload_size

  async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http" or scope["method"] != "POST":
      await self.app(scope, receive, send)
      return
    
    headers = Headers(scope=scope)
    content_length = headers.get("content-length")

    if content_length:
      try:
        if int(content_length) > self.max_upload_size:
          max_mb = self.max_upload_size / (1024 * 1024)
          response = JSONResponse(
            status_code=413,
            content={"detail": f"Payload Too Large. Maximum size is {max_mb:.1f} MB"}
          )
          await response(scope, receive, scope)
          return
      except (ValueError, TypeError):
        pass

    await self.app(scope, receive, send)
    