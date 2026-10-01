# 현재 상태 및 준비 진단

진단 기준일: 2026-10-01 (Asia/Seoul)

## 저장소 기준선

| 항목 | 확인 결과 |
|---|---|
| 원본 | `youtube-jocoding/shorts-multiuploader` |
| 원본 기본 브랜치 | `main` |
| 기준 커밋 | `dfb0523a94aac9762f17a2e4ff3227354564aaba` |
| 기준 Git tree | `7a4c4df2e9f6057b6e863a09cec29a0ec3dd3604` |
| LICENSE | MIT, 원본 보존 |
| LICENSE SHA-256 | `1DD75A3D6AE5EBCF35BB297EBCA563B957335DB6DAE90BE86A8EDF5374048312` |
| 대상 | `sorkwhaskrk-web/multiuploader` |
| 대상 초기 상태 | 이미 존재하는 빈 PUBLIC 저장소, 기본 브랜치 없음 |
| 로컬 작업 브랜치 | `feature/windows-bootstrap-audit` |

복제 직후 로컬 `HEAD`의 커밋과 tree는 원본 `upstream/main`과 동일했다. 따라서
원본 Git 이력과 LICENSE는 기준선에서 그대로 보존됐다. 이후 문서 변경은 기준
커밋 위의 기능 브랜치 커밋으로만 관리한다. `main`은 만들거나 수정하지 않는다.

## GitHub 및 자동화 상태

- GitHub CLI 활성 계정은 `sorkwhaskrk-web`로 확인했다.
- 대상 저장소가 이미 있어 새 저장소를 만들거나 덮어쓰지 않았다. 초기 원격 참조가
  없는 빈 저장소임을 확인한 뒤 작업했다.
- 대상 저장소는 PUBLIC이다. 운영 비밀이나 로컬 산출물을 절대 커밋하면 안 된다.
- 원본의 `.github/workflows/test.yml`은 모든 `push`와 `pull_request`에 반응한다.
  이번 단계에서는 GitHub Actions를 실행하지 않는다.
- 초기 확인 시 대상 저장소의 Actions 실행 이력은 0건이었다.

## 원본에서 확인한 기능

다음은 README 주장만이 아니라 소스와 테스트에서 확인한 원본 기능이다.

- `yt-dlp` 기반 YouTube Shorts 조회 및 다운로드
- `ffprobe` 검사 후 필요 시 `ffmpeg`로 H.264/AAC 정규화
- Instagram, Threads, TikTok, LinkedIn, Facebook, Naver Clip용 Playwright
  업로더 및 검증 모듈
- 선택 영상의 오래된 항목 우선 정렬
- `(youtube_id, platform)` 고유키를 사용하는 로컬 SQLite 중복 방지
- 플랫폼 레인별 장애 격리와 셀별 상태/증거/복구 브리프
- 게시 전 최종 텍스트 재검사와 선언형 콘텐츠 정책
- 로그인·권한·보안·법적 판단에서 실패 닫힘(fail closed)
- 실패 시 로컬 스크린샷/HTML 및 `data/runs/<run_id>/report.json` 생성

`AGENTS.md`와 `shorts-upload` 스킬도 검토했다. 핵심 불변 조건은 중복 업로드 금지,
정확한 게시 문구, 오래된 영상 우선, 콘텐츠 정책의 항상 적용, 플랫폼별 장애 격리,
로그인/2FA/CAPTCHA/저작권/권한 문제에서의 중단, `data/`와 `.env` 보호다.
## 현재 Codex 도구 상태

| 도구 범주 | 상태 | 이번 단계의 사용 범위 |
|---|---|---|
| 로컬 명령/Git/파일 검사 | 사용 가능 | 복제, 버전 진단, 테스트, diff 및 비밀 스캔 |
| GitHub CLI 및 GitHub 연동 | 사용 가능 | 인증·저장소·Actions 이력 확인과 기능 브랜치 전송 |
| 인터넷/웹 조회 | 사용 가능 | GitHub Actions의 `[skip ci]` 동작을 공식 문서로 확인 |
| Windows UI/브라우저 제어 | 도구는 등록됐으나 현재 초기화 실패 | SNS나 Chrome UI에는 접근하지 않음 |
| Codex 작업·자동화 관리 | 사용 가능하나 미사용 | 새 작업, 예약, heartbeat를 만들지 않음 |
| 문서·이미지·스프레드시트 도구 | 등록됨, 이번 범위 밖 | 사용하지 않음 |

현재 Codex 파일 패치 helper도 작업 경로와 별도 ASCII 임시 경로 모두에서 Windows
ACL 적용 오류로 실패했다. 문서 파일 작성은 승인된 로컬 셸로 범위를 고정해 수행했고
Git diff와 비밀 스캔으로 결과를 검증한다.

## Windows 환경 진단

| 구성 요소 | 실제 확인 결과 | 판정 |
|---|---|---|
| Windows | Windows 11 Pro 64-bit, build 26200 | 확인 |
| PowerShell | 7.6.5 | 확인 |
| Git | 2.54.0.windows.1, long paths 활성 | 확인 |
| GitHub CLI | 2.97.0, 대상 계정 인증됨 | 확인 |
| 전역 Python | Microsoft Store 실행 별칭만 존재, 실제 실행 불가 | 보완 필요 |
| `py` launcher | 설치되지 않음 | 선택 보완 |
| uv | 0.12.6 | 확인 |
| 프로젝트 Python | uv가 CPython 3.12.14 설치 및 `.venv` 생성 | 확인 |
| Chrome | 152.0.7977.83 (64-bit Program Files) | 확인 |
| ffmpeg/ffprobe | 9.0.1, `libx264` 포함 | 확인 |
| yt-dlp | 잠금 파일 버전 2026.3.17을 `.venv`에 설치 | 확인 |

### 실제 확인한 문제와 차단 사항

1. 표준 `uv sync --locked`가 이 PC의 Windows 애플리케이션 제어 정책에 의해
   차단된다. uv 빌드 격리 캐시의 임시 Python 실행 파일이 `os error 4551`로
   거부됐다. 의존성만 설치하는 `uv sync --locked --no-install-project`는 성공했다.
2. 전역 `python`과 `py`가 없으므로 uv 밖에서 문서의 Python 명령을 그대로 실행할
   수 없다. 프로젝트 실행은 uv 또는 `.venv\Scripts\python.exe`를 기준으로 해야
   한다.
3. Codex의 Windows UI/브라우저 제어 연결은 샌드박스 초기화 helper 실패로 현재
   사용할 수 없었다. Chrome 자체는 설치돼 있지만 UI 복구 도구의 실사용 검증은
   완료되지 않았다.
4. `.env`, 로그인 Chrome 프로필, 실제 콘텐츠 정책 파일, 게시 상태 DB가 없다.
   `doctor`는 종료 코드 3을 반환했고 `YOUTUBE_HANDLE`, Instagram 핸들,
   LinkedIn/Facebook 검증 URL, Naver 채널/카테고리 및 모든 플랫폼 로그인 프로필이
   준비되지 않았다고 보고했다.
5. 원본 README는 macOS를 주 테스트 환경으로 명시한다. Windows에서 실제 Chrome
   프로필 로그인, UI 선택자, 파일 업로드, 게시 및 직접 검증은 아직 검증되지 않았다.
6. Windows 터미널에서 `doctor --json`의 일부 한국어 힌트가 깨져 표시됐다. 운영
   로그 가독성을 위해 UTF-8 출력 설정을 고정할 필요가 있다.

## 수행한 로컬 검증

- 원본 기준 커밋과 tree 일치 확인: 통과
- LICENSE SHA-256 및 Git blob 보존 확인: 통과
- 추적 파일 민감 패턴 검색: 실제 값은 발견되지 않음. 쿠키 이름 상수만 검출됨
- 추적된 런타임 데이터 확인: `data/.gitkeep`, `data/downloads/.gitkeep`만 존재
- 단위 테스트: 9개 통과
- `python -m compileall -q src`: 통과
- 실제 SNS 게시: 수행하지 않음
- 예약 실행: 구성하지 않음
- GitHub Actions: 실행하지 않음

테스트는 콘텐츠 정책, Naver UTF-16 제목 제한, 플랫폼 장애 격리를 다룬다. 실제
Windows Chrome/Playwright 업로드, 계정 문맥, 파일 선택기, 게시 후 검증은 포함하지
않는다.

## 추가 제안

1. Windows 애플리케이션 제어 정책에서 uv의 빌드 격리 실행을 허용할지 조직 정책
   담당자와 결정하거나, 검증된 비격리 설치 절차를 프로젝트 표준으로 정한다.
2. PowerShell 실행 전 `$env:PYTHONUTF8='1'` 및 `$env:PYTHONIOENCODING='utf-8'`을
   설정해 한국어 로그 인코딩을 고정한다.
3. 실제 계정 정보 없이 Windows 전용 테스트를 추가한다: 경로/인코딩, Chrome 탐지,
   프로필 잠금, dry-run 보고서, ffmpeg 코덱 변환 테스트.
4. 첫 2편 게시 전 대상 플랫폼을 최소 집합으로 확정하고, 플랫폼별 비공개 테스트
   계정 또는 제한 공개 범위에서 한 셀씩 감독 실행한다.
5. 예약 실행은 2편의 모든 셀이 직접 검증된 뒤 별도 승인 단계로 둔다.

## 현재 결론

원본 복제와 로컬 정적·단위 검증은 수행했다. Windows 운영 환경은 부분 준비
상태이며, 애플리케이션 제어 정책, 로컬 계정 설정, 로그인 프로필, Codex UI 제어
연결이 남아 있다. 영상 2편의 다운로드·게시·플랫폼 직접 검증은 수행하지 않았으므로
배포 검증 완료 상태가 아니다.
