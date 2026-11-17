"""신규 판정 기준. 저장된 과거 알림의 판정은 변경하지 않습니다."""
from decimal import Decimal, InvalidOperation

WARNING_UM = Decimal("150")
DANGER_UM = Decimal("200")


def wear_level(wear):
    if wear is None:
        return None
    try:
        value = Decimal(str(wear))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value < 0:
        return None
    return "danger" if value >= DANGER_UM else "warning" if value >= WARNING_UM else "normal"


def alert_title(level, wear_type):
    kind = "".join(str(wear_type or "").lower().split())
    if kind in {"adhesion", "adhesion+flank", "flank+adhesion",
                "adhesion+flank_wear", "flank_wear+adhesion"}:
        advice = "공구 점검 필요"
    elif kind in {"flank", "flank_wear"}:
        advice = "공구 교체 필요" if level == "danger" else "감속 필요"
    else:
        advice = "마모 상태 확인"
    return f"{'위험' if level == 'danger' else '경고'} · {advice}"
