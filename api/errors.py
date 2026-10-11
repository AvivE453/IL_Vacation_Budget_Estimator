from pydantic import BaseModel


# The body of the API's own errors (404, 503), so the OpenAPI schema - and the
# TypeScript types generated from it - describes them too. 422s keep
# FastAPI's HTTPValidationError shape.
class ErrorDetail(BaseModel):
    detail: str


NOT_FOUND = {404: {"model": ErrorDetail, "description": "Not found"}}
SERVER_BUSY = {503: {"model": ErrorDetail, "description": "No free database connection; retry after Retry-After"}}
