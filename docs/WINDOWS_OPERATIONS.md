# Windows 운영 준비 안내

이 문서는 Windows에서 멀티업로더를 준비하고 첫 2편 검증으로 넘어가기 위한 운영
가이드다. 현재 단계에서는 실제 게시와 예약 실행을 하지 않는다.

## 1. 셸과 문자 인코딩

PowerShell 7을 저장소 루트에서 사용한다. 한글 로그가 깨지지 않도록 현재 세션에만
UTF-8을 적용한다.

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

비밀값은 PowerShell 기록이나 문서에 직접 붙여 넣지 않는다. `.env`는 로컬 편집기로
작성하고 Git 상태에서 무시되는지 확인한다.

## 2. 브랜치와 원격 확인

```powershell
git status --short --branch
git remote -v
```

작업 브랜치는 `feature/windows-bootstrap-audit` 또는 후속 기능 브랜치여야 한다.
`origin`은 `sorkwhaskrk-web/multiuploader`, `upstream`은 원본 저장소여야 한다.
`main`으로 전환해 직접 수정하거나 자동 병합하지 않는다.

## 3. Python 환경 구성

정상 경로는 다음과 같다.

```powershell
uv sync --locked
uv run python --version
```

현재 PC에서는 첫 명령이 Windows 애플리케이션 제어 정책의 `os error 4551`로
차단된다. 정책이 해결되기 전의 진단용 대안은 다음과 같다.

```powershell
uv sync --locked --no-install-project
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:PATH = "$(Resolve-Path .\.venv\Scripts);$env:PATH"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q src
```

이 대안은 설치 가능한 CLI 패키지를 만들지 않으므로 운영의 최종 해결책이 아니다.
애플리케이션 제어 정책을 임의로 해제하지 말고, 허용 정책 또는 서명된 실행 경로를
관리자와 확정한다.

## 4. 로컬 전용 설정

정책 문제가 해결된 뒤에만 `.env.example`을 `.env`로 복사한다. 다음 값은 반드시
실제 운영자 입력으로 채우며 추측하지 않는다.

- `YOUTUBE_HANDLE`
- `TARGET_PLATFORMS` — 첫 검증에서는 필요한 플랫폼만 명시
- 플랫폼별 계정 핸들 또는 검증 URL
- Naver를 쓸 경우 채널/Clip URL과 두 카테고리
- `PROFILE_STRATEGY`
- 광고 또는 캠페인 규칙이 있으면 로컬 `config/content-policies.json`

`SHORTS_UPLOAD_LIMIT=2`는 후보 수 상한일 뿐 게시 승인이 아니다. 실제 콘텐츠 정책은
명시적 영상 ID에도 적용된다.

설정 후 다음을 확인한다.

```powershell
git status --short --ignored
git check-ignore -v .env
```

`.env`, `config/content-policies.json`, `data/profiles/`, `data/runs/`, 다운로드 영상 및
DB가 Git에서 무시되어야 한다.

## 5. Chrome 프로필 준비

저장소 전용 프로필만 사용한다. 개인 기본 Chrome 프로필을 복사하거나 Git에 넣지
않는다. 같은 프로필을 일반 Chrome과 Playwright에서 동시에 열지 않는다.

로그인은 향후 명시적 승인 아래 플랫폼별로 수행한다.

```powershell
uv run shorts-dist login <platform>
```

로그인, 2FA, CAPTCHA, 계정 복구, 권한, 저작권 또는 광고 공개 선택은 사용자가 직접
확인해야 한다. 프로필은 `data/profiles/` 아래에만 저장하고 백업·전송·커밋하지 않는다.

## 6. 게시 없는 점검 순서

정상 CLI가 복구되고 로컬 설정이 준비된 후 아래 순서만 수행한다.

```powershell
uv run shorts-dist doctor --json
uv run shorts-dist plan --json
uv run shorts-dist run --dry-run --json
```

`doctor`와 `plan`은 게시하지 않는다. `run --dry-run`도 SNS에 게시하지 않지만, 선택한
영상을 다운로드하고 H.264로 변환할 수 있으며 `data/runs/`에 로컬 보고서를 쓴다.
따라서 저장 공간과 콘텐츠 권한을 확인한 뒤 실행한다.

dry-run 결과에서 다음을 검토한다.

- 정확히 의도한 두 영상인지
- 오래된 영상이 먼저인지
- 대상 플랫폼이 요청한 목록과 같은지
- `post_text`가 정확한지
- 광고/캠페인 정책과 공개 토글이 필요한지
- 영상 코덱이 H.264인지
- 모든 로그인 세션과 검증 URL이 올바른 계정 문맥인지

## 7. 첫 2편 실제 검증으로 넘어가는 게이트

다음 조건이 모두 충족되고 사용자가 실제 게시를 별도로 승인하기 전에는
`shorts-dist run` 또는 `shorts-dist upload`를 실행하지 않는다.

1. 표준 `uv sync --locked`와 CLI 실행이 Windows에서 정상 동작함
2. Codex UI 복구 도구 또는 동등한 수동 복구 경로가 준비됨
3. 대상 플랫폼과 계정 문맥이 사용자에 의해 확인됨
4. dry-run의 두 영상 ID, 순서, 문구, 정책이 승인됨
5. 플랫폼별 직접 검증 URL이 준비됨
6. 중복 게시 여부를 기존 플랫폼에서 먼저 확인함

실제 실행 단계에서도 한 플랫폼의 장애는 다른 플랫폼 레인에 전파하지 않는다.
게시 진행 표시가 있는 동안 창을 닫지 않고, 성공 후 플랫폼별 실제 게시물을 직접
검증한다. `missing`이 아닌 `inconclusive` 상태는 재업로드 허가가 아니다.

## 8. 예약 실행

예약 작업, Codex 자동화, Windows Task Scheduler 및 CI 기반 게시는 첫 2편의 모든
승인 대상 셀이 검증된 후 별도 설계·승인한다. 현재는 어떤 예약도 만들거나
활성화하지 않는다.

## 9. 운영 중단 및 비밀 보호

- 중단 요청 시 이 작업이 시작한 파이프라인과 자식 Playwright/Chrome 프로세스만
  종료하고, 사용자의 일반 Chrome 프로세스는 건드리지 않는다.
- 공개 이슈나 보고서에 스크린샷/HTML을 올리기 전에 계정 정보가 없는지 검토한다.
- 토큰, 쿠키 또는 프로필이 실수로 추적되면 게시를 중단하고 세션을 폐기·회전한 뒤
  Git 이력을 별도로 정리한다.
- DAYPICK, 기존 SNS 자동화, VPS 및 외부 DB는 이 저장소 운영 절차에 포함하지 않는다.
