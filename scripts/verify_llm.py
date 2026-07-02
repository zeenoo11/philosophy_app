"""'왜 빠른가 / LLM 실제로 거치나' 검증 — 결정론(ms) vs LLM(초) + MLflow 트레이싱.

uv run python scripts/verify_llm.py
"""
import time

from engine.interpret import interpret
from engine.narrator import narrate
from engine.pillars import BirthInput

birth = BirthInput(1990, 6, 15, 14, 30)

# 1) 결정론 + L2 + L3 — LLM 미사용(순수 파이썬). 이게 '빠른' 부분.
t0 = time.perf_counter()
r = interpret(birth)
det_ms = (time.perf_counter() - t0) * 1000
print(f"[결정론/L2/L3] interpret() = {det_ms:.1f} ms  (LLM 미사용, 순수 파이썬 계산)")
print(f"  → 8글자/십신/강약/용신/합충/신살을 즉시 산출. 앱에서 빠른 이유.\n")

# 2) L4 서술 — claude -p (실 LLM). 메타데이터로 실호출 증명.
block = r["by_preset"]["jeongtong_eokbu"]
print("[L4] claude -p (--output-format json) 호출 중... (수 초 소요)")
narr = narrate(block)
m = narr.meta
print(f"  모델           : {m['models']}")
print(f"  duration(claude): {m['duration_ms']} ms,  ttft: {m['ttft_ms']} ms,  wall: {m['wall_s']} s")
print(f"  토큰 in/out    : {m['input_tokens']} / {m['output_tokens']}")
print(f"  비용           : ${m['cost_usd']}")
print(f"  세션ID         : {m['session_id']}")
print(f"  그라운딩       : {narr.grounded}")
print(f"  서술(발췌)     : {narr.text[:110]}…\n")

if det_ms > 0 and m.get("duration_ms"):
    print(f"결론: LLM 1회 = 결정론의 약 {m['duration_ms']/det_ms:,.0f}배 느림(+토큰·비용 발생).")
print("      ⇒ '빠른 것'은 LLM을 거치지 않는 결정론 부분. LLM(L4)은 앱에서 기본 OFF였음.")
print("MLflow 트레이스 저장: ./mlruns  (조회: uv run mlflow ui --backend-store-uri ./mlruns)")
