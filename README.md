# Art Style

이미지에서 **화풍**과 **캐릭터 외형**을 분리해 재사용할 프롬프트를 만들고 보관하는 개인 작업실입니다.

- 1~8장, 합계 30MB. 첫 이미지를 기준으로 공통 규칙과 변형·충돌을 구분합니다.
- 선택 사항인 Codex 자동 분석, 또는 외부 챗봇용 JSON 요청문 복사.
- 외부 챗봇 응답 전체 붙여넣기 → 형식 확인 → 이미지와 원래 JSON 저장.
- 제목·파일명 검색, 프롬프트 복사, JSON·이미지 다운로드, 재분석과 라이브러리 기록 삭제.
- 이미지 방향 보정, 최대 3072px WebP, EXIF 제거. 원본은 영구 저장하지 않습니다.
- 웹의 **사용 가이드**(`/guide`)에서 Codex 연결과 JSON 사용법을 확인합니다.

## 실행

Docker Compose와 Python 3.10 이상을 준비합니다.

```sh
python tools/setup.py
docker compose up -d --build
```

기본 주소는 `http://localhost:8080`입니다. 설정 도구에서 생성한 작업실 아이디·암호로 로그인하세요. 기본 실행은 **Codex가 필요 없는 JSON 라이브러리**이며 로컬 CLI 설치도 필요 없습니다.

설정 도구는 기존 `.env`를 덮어쓰지 않습니다. 새 외부 HTTPS 주소를 사용할 경우 처음부터 해당 주소를 지정하세요.

```sh
python tools/setup.py --url https://artstyle.example.com --username admin --port 8080
```

도메인의 HTTPS 역방향 프록시는 호스트의 `127.0.0.1:8080`으로 연결합니다. `APP_URL`은 브라우저가 쓰는 정확한 origin이어야 합니다. 운영 HTTPS에서는 `COOKIE_SECURE=true`를 유지하세요. 쿠키와 요청 출처 검사를 우회해서 배포하지 마세요.

## Codex 자동 분석 추가

```sh
docker compose --profile codex up -d --build
```

웹 **설정 → ChatGPT로 연결**에서 발급된 코드를 OpenAI 인증 페이지에 입력합니다. OpenAI 암호·API 키를 이 앱에 입력하지 않습니다. 필요한 계정에서는 ChatGPT 보안 설정/워크스페이스 권한의 기기 코드 로그인을 먼저 허용해야 합니다. 연결 후 모델·추론 정도·언어를 선택합니다. 자동 분석은 연결한 계정의 Codex 사용량을 소비하며 Image API를 호출하지 않습니다. [공식 인증 안내](https://developers.openai.com/codex/auth)

이 앱의 웹 로그인과 Codex 연결은 별개입니다. 인증 파일은 `runner`의 전용 `codex` 볼륨에만 보관합니다. 웹 백엔드에는 CLI나 인증 볼륨이 없습니다.

## 외부 챗봇 JSON 사용

1. **새 분석**에서 이미지를 선택하고 **외부 도구용 JSON**을 누릅니다.
2. 보통의 대화형 챗봇에는 **이미지 별도 첨부**를 선택합니다. 요청문을 붙여넣고 표시된 이미지를 순서대로 모두 첨부합니다.
3. 챗봇이 반환한 `style_prompt`/`character_prompt` 응답을 복사합니다. 요청문 자체를 다시 가져오면 안 됩니다.
4. **JSON 가져오기**에서 같은 이미지와 응답을 넣고 확인 후 저장합니다. json 코드 블록이나 짧은 설명이 붙은 응답도 인식합니다.
5. 저장한 기록에서는 원래 응답 JSON과 최적화 이미지를 다시 받을 수 있습니다.

`input.images`를 포함한 요청 명세는 특정 서비스 API의 HTTP 본문이 아닙니다. API 연동 시 해당 도구의 이미지·지침·응답 형식 필드에 맞춰야 합니다. Base64 이미지 포함 방식은 받는 도구가 실제 이미지로 해석할 수 있을 때만 사용하세요. 외부 도구·모델에 따라 결과는 달라집니다.

## 구성과 보안 경계

| 서비스 | 역할 | 접근하는 비밀값/데이터 |
| --- | --- | --- |
| frontend | 정적 웹·프록시 | 인증 정보 없음 |
| backend | 라이브러리·요청 검증 | 전용 DB 역할, 이미지, 내부 실행기 토큰 |
| db | PostgreSQL 17 | 별도 관리자 암호와 앱 역할 |
| runner (선택) | 제한된 Codex 작업 | Codex 인증/바이너리, 내부 토큰. DB·라이브러리 볼륨 없음 |

DB·백엔드·실행기 포트는 호스트에 공개하지 않습니다. 백엔드와 DB는 내부 네트워크만 사용하며, 실행기는 DB 네트워크에 연결되지 않습니다. 실행기에는 임의 명령·파일 경로·URL·JSON-RPC를 전달하는 웹 API가 없습니다. 업로드와 가져오기는 인증·출처·실제 본문 크기를 파싱 전에 확인하며, 외부 JSON은 코드나 HTML로 실행하지 않습니다.

서버별 Compose override에서 네트워크 주소 풀을 바꾸는 경우 내부 통신망의 `internal: true`도 명시하세요. Compose 버전과 병합 결과에 따라 속성이 달라질 수 있으므로 배포 후 `docker network inspect`로 실제 적용을 확인합니다. 개인 override 파일은 공개 준비본에서 제외합니다.

하나의 설치는 하나의 작업실 계정과 라이브러리를 공유합니다. 다중 사용자 SaaS의 계정별 격리 구조가 아닙니다. 작업실에 로그인할 수 있는 사람은 그 설치의 기록과 Codex 연결을 사용할 수 있으므로 접속 암호는 신뢰하는 운영자에게만 제공하세요. 상세 점검 내용과 남는 범위는 [SECURITY.md](SECURITY.md)를 참고하세요.

## 기존 설치 업그레이드

DB·이미지·Codex 볼륨과 `.env`를 먼저 백업합니다. 기존 단일 컨테이너 방식에서 옮기는 경우 `.env`에 서로 다른 임의 `APP_DB_PASSWORD`(64자리 hex), `ENGINE_TOKEN`(32자 이상)을 추가해야 합니다. 이전 DB 소유자 권한으로 `tools/bootstrap_db.py`를 한 번 실행해 앱 전용 역할과 테이블 소유권을 준비한 후 새 Compose를 올립니다. 관리자 DB 암호를 새 웹 백엔드에 전달하지 마세요. `codex`, `codex-bin` 볼륨 이름은 유지되어 기존 인증을 재사용합니다. 컨테이너 재생성 후 웹을 새로고침하세요.

분석은 순차 처리하고 최대 20개를 대기시킵니다. 서버 재시작 중 실행하던 분석은 실패로 표시하며 다시 분석할 수 있습니다. 브라우저 세션은 수동 로그아웃 전까지 서버에서 자동 만료시키지 않으며, 브라우저 쿠키 정리나 공유 PC의 쿠키 유출은 별도로 주의해야 합니다.

## 개발과 검증

```sh
python -m venv .venv
# 가상환경을 활성화한 뒤:
pip install -r backend/requirements.txt
python -m unittest discover -s tests
node --test frontend/src/external-request.test.js frontend/src/image-selection.test.js
npm ci --prefix frontend
npm run build --prefix frontend
```

저장·마이그레이션 통합 검증은 테스트 전용 PostgreSQL을 사용합니다. `ADMIN_DATABASE_URL`을 임시 DB 생성/삭제 권한이 있는 테스트 DB로 지정해 `tests/integration_storage.py`를 실행합니다. 운영 DB 관리자 암호를 웹 서비스 환경에 넣지 마세요.

```sh
pip install pip-audit
pip-audit -r backend/requirements.txt
npm audit --prefix frontend
python tools/check_public.py
python tools/build_release.py
```

저장소에는 `.env`, 인증 파일, DB 덤프, 실제 이미지·기록·로그, 개인 배포 스크립트를 포함하지 않습니다. `check_public.py`는 Git에 등록된 파일을 검사하며, `build_release.py`도 같은 파일만 패키징합니다. 공개 커밋에는 개인 이메일 대신 GitHub 비공개 이메일을 사용하세요. 별도 라이선스 파일은 아직 추가하지 않았습니다.

[화풍 추출 원칙과 공개 공유 글 검토](docs/style-extraction.md)
