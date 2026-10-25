from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.i18n import t
from app.core.logging import logger


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ErrorResponse(BaseModel):
    detail: str


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        logger.warning(
            "API error request_id={} status={}",
            getattr(request.state, "request_id", "unknown"), exc.status_code,
        )
        return JSONResponse(status_code=exc.status_code, content=ErrorResponse(detail=exc.message).model_dump())

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled error request_id={} type={}",
            getattr(request.state, "request_id", "unknown"), type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(detail=t("internal_server_error")).model_dump(),
            headers={"X-Request-ID": getattr(request.state, "request_id", "unknown")},
        )
