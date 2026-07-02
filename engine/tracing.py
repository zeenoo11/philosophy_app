"""LLMOps 트레이싱 — MLflow. LLM(claude -p) 호출의 프롬프트·응답·모델·토큰·
비용·지연을 span 으로 기록한다. 'LLM 을 실제로 거치는가'의 감사(audit) 근거.

비활성/실패에 안전: SAJU_TRACE=0 이거나 mlflow 미설치/오류 시 no-op span 반환
(서술 자체는 절대 깨지지 않음). 트레이스 저장은 SQLite 백엔드(mlflow.db)
— MLflow 3.x 는 file store 를 폐기했으므로 sqlite 사용.
조회:  uv run mlflow ui --backend-store-uri sqlite:///mlflow.db  → http://localhost:5000
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

_DB = (Path(__file__).resolve().parent.parent / "mlflow.db")
_TRACKING = "sqlite:///" + str(_DB).replace("\\", "/")  # 윈도우 경로 → sqlite URI
_EXPERIMENT = "saju-narration"
_setup_done = False


def tracking_uri() -> str:
    return _TRACKING


def _ensure_setup() -> None:
    global _setup_done
    if _setup_done:
        return
    import mlflow
    mlflow.set_tracking_uri(_TRACKING)
    mlflow.set_experiment(_EXPERIMENT)
    _setup_done = True


class _NoopSpan:
    def set_inputs(self, *_a, **_k): pass
    def set_outputs(self, *_a, **_k): pass
    def set_attributes(self, *_a, **_k): pass
    def set_attribute(self, *_a, **_k): pass


def tracing_enabled() -> bool:
    return os.environ.get("SAJU_TRACE", "1") != "0"


@contextmanager
def llm_span(name: str, inputs: dict, *, enabled: bool = True):
    """LLM 호출용 MLflow span. 실패해도 서술을 막지 않는다."""
    if not (enabled and tracing_enabled()):
        yield _NoopSpan()
        return
    try:
        import mlflow
        _ensure_setup()
        with mlflow.start_span(name=name, span_type="LLM") as span:
            try:
                span.set_inputs(inputs)
            except Exception:  # noqa: BLE001
                pass
            yield span
    except Exception:  # noqa: BLE001 — mlflow 미설치/오류 시 무력화
        yield _NoopSpan()
