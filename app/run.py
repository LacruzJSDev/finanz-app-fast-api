import uvicorn

from app.config import settings
from app.logging_config import build_log_config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT != "production",
        log_config=build_log_config(),
    )
