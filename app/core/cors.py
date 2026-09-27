"""CORS for the dashboard's API, except the public chat routes, which answer each widget's own websites
(see app/routers/widgets.py)."""
from starlette.middleware.cors import CORSMiddleware

PUBLIC_PATHS = ("/api/public/", "/widget.js")


class AppCORSMiddleware(CORSMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith(PUBLIC_PATHS):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)
