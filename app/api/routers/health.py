from fastapi import APIRouter

router = APIRouter()

#서버 응답 확인
@router.get("/health")
def health():
    return {"status": "ok"}

#프론트엔드에서 백엔드 연결
@router.get("/api/test")
def api_test():
    return {"message": "Backend connected"}