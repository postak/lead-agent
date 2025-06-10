"""Main application for the Lead Qualification Voice Agent."""

from absl import logging
import dotenv
import fastapi
from src.api import calls
from src.api import streams
from src.config import settings

load_dotenv = dotenv.load_dotenv
FastAPI = fastapi.FastAPI

load_dotenv()


# --- Logging and App Setup ---
logging.set_verbosity(logging.INFO)
logging.use_absl_handler()

app = FastAPI(title=settings.APP_NAME)
app.include_router(calls.router)
app.include_router(streams.router)


@app.get("/")
async def root():
  logging.info("Root path '/' accessed.")
  return {"message": "Lead Qualification Voice Agent API is running."}


if __name__ == "__main__":
  import uvicorn  # pylint: disable=g-import-not-at-top

  uvicorn.run(
      "main:app",
      host="0.0.0.0",
      port=8080,
      reload=True,
  )
