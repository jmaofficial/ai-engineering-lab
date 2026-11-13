from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.api.chat import router as chat_router
from app.api.agent import router as agent_router

app = FastAPI()

app.include_router(chat_router)
app.include_router(agent_router)

static_directory = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_directory), name="static")


@app.get("/", include_in_schema=False)
def chat_ui():
    return FileResponse(static_directory / "index.html")
