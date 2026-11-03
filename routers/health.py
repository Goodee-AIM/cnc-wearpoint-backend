from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/api/test")
def api_test():
    return {"message": "Backend connected"}