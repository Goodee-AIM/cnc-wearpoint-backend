import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="CNC WearPoint API")

origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET"],
    allow_headers=[],
    allow_credentials=False,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/test")
def api_test():
    return {"message": "Backend connected"}