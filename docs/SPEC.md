# 사주 앱 — 다중 유파 해석 엔진 설계 & 검증 스펙
> Claude Code 핸드오프용 스펙. 이 문서를 리포 루트에 두고 `docs/SPEC.md`로 참조하면서 작업.
> 핵심 명제: **계산은 정답이 있고, 해석은 정답이 없다.** 두 레이어는 문서화·검증 방식이 완전히 달라야 한다.
---
## 0. 설계 원칙 (가장 중요)
1. **결정론 레이어와 해석 레이어를 코드·테스트·CI에서 물리적으로 분리한다.**
   같은 파일/모듈에 섞이면 검증 철학이 오염된다.
2. **"하나의 정답"을 내지 않고 "유파별 분기"를 드러내는 것을 1급 기능으로 삼는다.**
   해석 출력은 단일 결론이 아니라 *프리셋 태그가 붙은 결론들의 집합*이다.
3. **모든 해석 문장은 출처추적(provenance)을 갖는다.** 어떤 규칙이, 어떤 프리셋 파라미터로, 어떤 고전 근거에서 나왔는지 추적 불가능한 문장은 출력 금지.
4. **유파 = 파라미터 프리셋.** 새 유파 추가가 코드 수정이 아니라 설정 파일 추가로 끝나야 한다.
---
## 1. 아키텍처 (4레이어)
```
[L1] 결정론 엔진 (pillars-core)      ← 정답 있음. 천문/룩업/산술
      입력: 생년월일시 + tz + 경도 + (이산 이론 토글)
      출력: 8글자, 지장간, 십신, 합충형파해, 십이운성, 신살
        │
        ▼
[L2] 스코어링 (strength-scorer)      ← 규칙 있으나 가중치는 프리셋
      신강/신약 점수, 왕상휴수사, 통근 점수
        │
        ▼
[L3] 용신 선정기 (yongsin-policy)    ← 정책 분기. 정답 없음
      억부/조후/병약/통관/전왕 정책을 함수로, 우선순위는 프리셋
      (맹파 프리셋은 이 레이어를 우회 — 용신 대신 주공/상 구조 산출)
        │
        ▼
[L4] 자연어 종합 (narrator)          ← LLM. L1~L3의 구조화 결과만 입력
      서술 생성. 단, trace에 없는 사실은 언급 금지
```
레이어별 진리조건:
| 레이어 | 정답 존재? | 검증 목표 |
|---|---|---|
| L1 결정론 | **있음** | 정확성 (만세력·천문력 대조) |
| L2 스코어링 | 부분적 | 규칙 준수 + 단조성 invariant |
| L3 용신 | **없음** | 유파 충실도(내적 무모순) + 결정성 |
| L4 서술 | 없음 | 그라운딩(환각 차단) + 결정성 |
---
## 2. 문서화 전략
### 2.1 유파 = 프리셋 레지스트리
각 유파를 YAML 한 파일로. 결정론 토글과 해석 정책을 한 곳에 모은다.
```yaml
# presets/jeongtong_eokbu.yaml — 정통 자평 · 억부 우선 (한국 표준 계열)
preset_id: jeongtong_eokbu
display_name: "정통 자평 (억부 중심)"
lineage: "자평진전 + 적천수 / 서락오 주석"
description: "신강·신약 판정 후 억부용신을 1순위로 잡는 가장 보편적 계열"
deterministic:                        # ← 출력 '글자'가 바뀌는 이산 토글
  sipiunseong_theory: eumyang_sunyeok # 음양순역설 | dongsaeng_dongsa | sutodonggung
  woryulbunya_theory: japyeongjinjeon # myeongni_chumyeong | japyeongjinjeon | sammyeongtonghoe
  jasi_rule: yajasi_split             # 야자시 분리 | jasi_unified
  true_solar_time: true               # 진태양시(경도) 보정
  longitude_deg: 127.0
interpretation:                       # ← 해석 정책
  sinkang_weights: { woljji: 3.0, ilji: 1.5, others: 1.0 }
  yongsin_policy: [eokbu, johu, byeongyak]   # 우선순위 = 정책 분기
  use_sinsal: true
  use_mulsang: false
```
```yaml
# presets/mangpa.yaml — 맹파명리 (대조군: L3를 우회)
preset_id: mangpa
display_name: "맹파명리 (단건업 계열)"
lineage: "단건업 / 박형규 전달"
deterministic:
  sipiunseong_theory: eumyang_sunyeok
  woryulbunya_theory: sammyeongtonghoe
  jasi_rule: jasi_unified
  true_solar_time: true
  longitude_deg: 127.0
interpretation:
  engine: structure          # ← 용신 엔진 자체를 바꿈
  yongsin_policy: null       # 용신·기신 미사용
  features: [jugong, sang, binju, cheyong]   # 주공/상/빈주/체용
  use_sinsal: false
  use_mulsang: true
```
문서화 규칙: **프리셋 파일 = 그 유파의 명세서.** 별도 산문 설명서를 따로 두지 않는다. 사람이 읽을 근거(`lineage`, `description`)와 기계가 읽을 파라미터를 한 파일에 둬야 드리프트가 없다.
### 2.2 출처추적(provenance) 객체
모든 해석 결과 문장이 들고 다녀야 하는 메타데이터:
```json
{
  "claim": "이 사주는 신약하여 인성·비겁의 도움이 필요합니다",
  "trace": {
    "rule_id": "eokbu.weak.support",
    "preset_id": "jeongtong_eokbu",
    "inputs": { "sinkang_score": 2.1, "threshold": 3.0 },
    "classical_source": "적천수 / 서락오 주석",
    "layer": "L3"
  }
}
```
이게 있으면 ① UI에서 "왜 이렇게 나왔나"를 펼쳐 보여줄 수 있고, ② L4 서술 검증의 기준이 되며, ③ 유파 간 차이를 자동으로 diff할 수 있다.
### 2.3 불일치 우선(disagreement-first) 출력 계약
해석 API는 단일 결론이 아니라 다음을 반환한다:
```json
{
  "deterministic": { "...8글자·십신·합충 (프리셋 무관 공통)..." },
  "by_preset": {
    "jeongtong_eokbu": { "yongsin": "水", "trace": {...} },
    "johu_centered":   { "yongsin": "火", "trace": {...} },
    "mangpa":          { "structure": {...}, "trace": {...} }
  },
  "agreement": { "deterministic": "full", "yongsin": "diverged" }
}
```
`agreement` 필드가 "어디서 갈렸는지"를 명시 → 앱이 합의된 부분과 갈린 부분을 시각적으로 구분해 보여줄 수 있다.
---
## 3. 검증 전략
### 3.0 검증 철학 매트릭스
| 테스트 유형 | 대상 레이어 | 전제하는 진리조건 | 도구 |
|---|---|---|---|
| 골든 코퍼스 대조 | L1 | 외부 정답 존재 | pytest fixtures |
| 천문 경계 검증 | L1 | 천문력이 정답 | skyfield / sxtwl |
| 속성 기반 | L1 | 구조적 불변식 | hypothesis |
| 엣지 매트릭스 | L1 | 알려진 함정 | 수기 케이스 |
| 교차 출처 차분 | L1 | 합의=정답, 불합치=이론차 | sxtwl + 자체엔진 |
| 단조성 invariant | L2 | 내적 일관성 | hypothesis |
| 유파 충실도 | L3 | **정답 아닌 규칙 준수** | pytest |
| 차분 기대 | L3 | 갈려야 할 곳만 갈림 | pytest |
| 출처 완전성 | L3 | orphan 금지 | pytest |
| 그라운딩 | L4 | trace 외 사실 금지 | NER/LLM judge |
> 핵심: **L3·L4에는 `assert 용신 == "水"` 같은 정확성 테스트를 절대 쓰지 않는다.** 정답이 없으므로 그건 특정 유파를 정답으로 박제하는 것일 뿐이다. 대신 "규칙을 지켰는가"만 검증한다.
### 3.1 L1 결정론 — 정답이 있는 레이어
**(a) 골든 코퍼스** — 신뢰 가능한 만세력 N개 기준 차트를 fixture로 고정. 일반 + 엣지 포함.
**(b) 천문/경계 검증** — 절기 입절(立節) 시각은 표 룩업이 아니라 **태양 황경 15° 교차 순간**(천문 계산)으로 검증.
**(c) 속성 기반 (hypothesis)** — 60갑자 연속성, 범위, 오호둔/오자둔.
**(d) 엣지케이스 매트릭스 (한국 특수사항)**
| 케이스 | 함정 | 검증 포인트 |
|---|---|---|
| 입춘 절입 순간 전후 | 연주가 바뀜 (1/1 아님) | 입절 시각 분 단위 |
| 절기 경계 출생 | 월주가 바뀜 | 태양황경 교차 시각 |
| 야자시/조자시 (23–01시) | 날짜 경계 모호, 유파별 상이 | `jasi_rule` 토글 동작 |
| 진태양시 보정 | 동경 135° vs 실제 ~127° → 약 30분 | 경도 보정 on/off |
| 균시차 (equation of time) | 최대 ±16분 | 시주 경계 출생 |
| **한국 표준시 변경 이력** | UTC+8:30 ↔ UTC+9 역사적 변동 | **UTC+9 하드코딩 금지** |
| **서머타임 연도** | 1948–51, 55–60, 87–88 등 | 표준 오프셋 맹신 금지 |
| 윤달 | 음력 기능 쓸 경우 | 윤달 처리 |
> ⚠️ 시간 처리는 직접 오프셋 계산하지 말고 **IANA `Asia/Seoul` tz 데이터를 신뢰 소스로** 사용. 역사적 오프셋 변경과 서머타임이 이미 인코딩돼 있다. 그 위에 진태양시(경도) 보정만 추가로 얹는다.
**(e) 교차 출처 차분 (oracle 검증)** — 같은 입력을 자체 엔진 + 독립 라이브러리(`sxtwl`)에 동시 투입:
- **간지·절기가 일치해야 하는 부분** → assert (불일치 = 자체 엔진 버그)
- **합법적으로 갈리는 부분**(십이운성·월률분야 등) → diff 리포트
### 3.2 L3 해석 — 정답이 없는 레이어
**(a) 결정성/멱등성** — 같은 (차트, 프리셋)은 항상 동일 출력. snapshot(`syrupy`).
**(b) 유파 충실도 (invariant)** — "엔진이 자기 규칙을 지켰는가"만. 신강↔설기/극제, 신약↔부조.
**(c) 차분 기대** — 갈려야 할 곳에서만 갈리는지. 결정론 레이어는 프리셋 무관 동일.
**(d) 출처 완전성** — trace 없는 해석 문장 0건을 CI 게이트로.
### 3.3 L4 서술 — 환각 차단
LLM 종합기는 **L1~L3의 구조화 결과(verdict + trace)만** 입력. trace 외 개체/주장 금지.
---
## 4. 단계별 테스트 플랜 (Claude Code 작업 순서)
| 단계 | 범위 | 게이트 |
|---|---|---|
| **P0** | L1 골든 코퍼스 (일반 케이스) | 100% 통과 후 다음 단계 |
| **P1** | L1 속성 기반 테스트 | 60갑자 연속성·범위·오호둔/오자둔 |
| **P2** | L1 엣지 매트릭스 (입춘·절기·야자시·tz) | 각 케이스 명시적 테스트 |
| **P3** | L1 교차 출처 차분 (sxtwl oracle) | 간지/절기 합치 + diff 리포트 산출 |
| **P4** | L3 유파 충실도 + 차분 기대 | 프리셋별 invariant 통과 |
| **P5** | L4 그라운딩 | trace-외 개체 0건 |
> **테스트 게이트 원칙:** P0~P3(결정론)이 다 녹색이 되기 전에는 P4~P5(해석)를 손대지 않는다. 계산이 틀리면 해석 검증은 무의미하다.
---
## 5. 리포지토리 구조
```
saju-engine/
├─ docs/SPEC.md                  # 이 문서
├─ docs/schools.md               # 유파(학파) 근거 자료 — 원전·인물·출처 + 토글 매핑
├─ presets/                      # 유파 = 프리셋 (YAML) — 7종
│  ├─ jeongtong_eokbu / johu_centered / jeonwang_tonggwan / mangpa  (기존 4)
│  ├─ byeongyak_sinbong(명리정종 병약) / sammyeong_gobeop(삼명통회 고법)
│  ├─ sinpa_dongsaeng(현대 신파 동생동사)                            (신규 3)
├─ engine/
│  ├─ pillars.py                 # L1 결정론 (순수 함수)
│  ├─ astro.py / timeutil.py / constants.py / relations.py / sinsal.py
│  ├─ scorer.py                  # L2
│  ├─ yongsin/                   # L3 (정책별 함수)
│  └─ narrator.py                # L4 (LLM 호출 + 그라운딩 가드)
├─ fixtures/golden/*.json        # 기준 차트 (엣지 포함)
└─ tests/
   ├─ deterministic/             # L1: golden, property, edge, cross-source
   └─ interpretation/            # L3/L4: fidelity, differential, grounding
```
권장 도구: `hypothesis`(속성), `syrupy`(스냅샷), `sxtwl`(천문 oracle), `skyfield`(절기 입절 시각). 한국 절기/음양력 권위 데이터는 KASI(한국천문연구원) 자료로 교차 확인.
---
## 6. 새 유파 추가 체크리스트
- [ ] `presets/<id>.yaml` 추가 (lineage·description·파라미터)
- [ ] 그 유파의 **invariant**를 `tests/interpretation/test_<id>_fidelity.py`에 1개 이상
- [ ] 기존 프리셋과의 **차분 기대** 1개 추가
- [ ] L3 정책이 기존 함수로 표현 불가하면 `yongsin/<id>.py` 추가 (맹파처럼 엔진 교체형만)
- [ ] 골든 코퍼스 일부 케이스에 대해 출력 스냅샷 생성
---
## 7. 안티패턴 (하지 말 것)
1. **단일 만세력 앱을 "정답"으로 삼아 그것과 일치=정답으로 검증** → 천문 oracle + 복수 출처 차분으로.
2. **L3/L4에 정확성(accuracy) 테스트 작성** → 정답 없는 영역에 거짓 기준.
3. **UTC+9 하드코딩** → 역사적 오프셋·서머타임 무시. IANA tz 사용.
4. **결정론과 해석을 같은 함수에** → 검증 철학 오염.
5. **trace 없는 해석 문장 출력** → 출처 불명 주장 양산.
6. **표 룩업만으로 절기 처리** → 경계 출생에서 틀림. 천문 계산 병행.
---
*요약: 결정론 레이어는 천문 oracle로 "정확성"을, 해석 레이어는 invariant로 "규칙 충실도"를 검증한다. 유파의 다양함은 프리셋 레지스트리 + disagreement-first 출력으로 드러내고, 모든 해석은 trace로 출처를 보증한다.*
