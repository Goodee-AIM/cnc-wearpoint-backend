from fastapi import FastAPI

app = FastAPI(title="CNC WearPoint API")


@app.get("/health")
def health():
    return {"status": "ok"}