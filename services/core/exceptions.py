from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from gbil.errors import GbilError


def register_handlers(app: FastAPI) -> None:

    @app.exception_handler(GbilError)
    async def gbil_error_handler(
        request: Request,
        exc: GbilError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_handler(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Database error"},
        )

    @app.exception_handler(Exception)
    async def global_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
