# Portainer 배포 — GitHub → 자동 포팅 (GitOps)

哲命 플랫폼을 Portainer **Git 스택**으로 올린다. GitHub 에 push 하면
Portainer 가 감지해 자동으로 re-pull + 재배포한다(GitOps updates).

## 준비물

- 서버에 Docker + Portainer CE 2.19+ (GitOps updates 기능 포함)
- 이 저장소의 GitHub 원격 (예: `https://github.com/zeenoo11/philosophy_app`)
- OpenRouter API 키 (LLM 리포트용 — 없으면 결정론 기능만 동작)
- 호스트 아키텍처 **amd64** 권장 — 사주 절기 계산의 `sxtwl` 휠이 amd64 전용.
  ARM 서버는 qemu 에뮬레이션이 필요해 느리다.

## 1) 스택 만들기

Portainer → **Stacks → + Add stack** →

| 항목 | 값 |
|---|---|
| Name | `cheolmyeong` (원하는 이름) |
| Build method | **Repository** |
| Repository URL | `https://github.com/zeenoo11/philosophy_app` |
| Repository reference | `refs/heads/main` (배포 브랜치) |
| Compose path | `docker-compose.yml` |
| Authentication | 비공개 repo 면 GitHub PAT(**repo read 권한**) 입력 |

> 이미지 이름/포트를 바꿀 필요 없다 — compose 가 `PLATFORM_PORT`(기본 8123)로
> 열고, 리버스 프록시(Caddy/Traefik/Nginx)를 앞에 두는 걸 권장한다.

## 2) Environment variables (스택 화면 하단)

`.env` 파일은 저장소에 없으므로(시크릿), 스택 환경변수로 주입한다:

| 변수 | 필수 | 설명 |
|---|---|---|
| `OPENROUTER_API_KEY` | 권장 | LLM 리포트/철학 대화. 비우면 결정론 기능만 |
| `CHAINLIT_AUTH_SECRET` | 권장 | 로그인 모드 활성화(계정별 저장·/me·통합 리포트). 생성: `uv run chainlit create-secret` |
| `PLATFORM_PORT` | 선택 | 호스트 포트 (기본 8123) |
| `SAJU_TRACE` | 선택 | MLflow 트레이싱 (기본 0) |

모델/백엔드 오버라이드(`SAJU_LLM_MODEL` 등)는 compose 의 주석을 해제한 뒤
같은 방식으로 추가한다. **빈 문자열로 두면 안 됨**(주석 참고).

## 3) GitOps updates (자동 포팅) 켜기

스택 생성 화면(또는 생성 후 스택 → **Editor** 탭 옆 설정)에서:

- **GitOps updates** 토글 ON
- Mechanism:
  - **Polling** — 가장 간단. Fetch interval `5m` 정도면 충분.
  - **Webhook** — push 즉시 반영. Portainer 가 보여주는 webhook URL 을 복사해
    GitHub repo → Settings → Webhooks → Add webhook 에 붙인다
    (Content type `application/json`, 이벤트 `Just the push event`).
- **Re-pull image and redeploy**: 이 스택은 저장소에서 **빌드**하므로
  push 가 오면 Portainer 가 재빌드 후 재배포한다.

> 첫 빌드는 오래 걸린다(의존성 + 천문력 + 임베딩 모델 베이크, 수 분).
> 이후는 Docker 레이어 캐시로 소스 변경분만 다시 빈다.

## 4) 확인

- `http://<host>:8123/health` → `{"status":"ok"}`
- `http://<host>:8123/` 랜딩 — 우상단 **KO·EN** 토글 동작
- `/app` 채팅 — 프로필(🔮 사주 · Saju / 🧭 철학 · Philosophy),
  웰컴의 **🌐 English** 버튼으로 영어 모드
- 컨테이너 헬스체크: Portainer 컨테이너 목록에서 `healthy` 뱃지

## 데이터 영속성

사용자 DB(계정·사주 프로필·철학 진단·리포트 기록)는 named volume
**`platform-db`** (`/app/data/saju.db`)에 있다. 재배포/재빌드에도 유지되고,
스택을 **삭제**할 때만 volume 정리 여부를 묻는다. 백업:

```bash
docker run --rm -v cheolmyeong_platform-db:/data -v $PWD:/backup alpine \
  cp /data/saju.db /backup/saju-$(date +%F).db
```

## 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| 빌드 실패: `sxtwl` 휠 없음 | ARM 호스트 — amd64 서버 사용 또는 qemu binfmt 설치 |
| LLM 리포트가 "생성 실패" | `OPENROUTER_API_KEY` 미설정/잔액 부족. 스택 env 확인 |
| /me 가 503 | `CHAINLIT_AUTH_SECRET` 미설정 — 익명 모드 |
| push 해도 반영 안 됨 | GitOps 토글/브랜치(ref) 확인, webhook 이면 GitHub delivery 로그 확인 |
| 포트 충돌 | `PLATFORM_PORT` 변경 |
