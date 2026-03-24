# claude-conversation-logger

[English](README.md) | **한국어**

Claude Code 세션을 자동으로 읽기 좋은 마크다운 파일로 저장하는 플러그인입니다.

Claude가 응답을 완료할 때마다 현재 세션이 디스크에 기록됩니다. 컨텍스트 압축으로 인한 대화 유실 없이, 언제든 과거 대화를 다시 확인할 수 있습니다.

## 기능

- Claude 응답마다 세션을 `.md` 파일로 저장
- 프로젝트 이름별 하위 디렉토리로 정리
- 파일명에 세션 시작 시각 포함
- Extended thinking(`<details>` 블록)을 접을 수 있는 섹션으로 보존
- Claude Code 내부 시스템 태그는 제거하고 실제 대화만 저장

**로그 저장 위치:**
```
~/.claude/conversation-logs/
  my-project/
    2026-03-24_13-04-37_0024fc91.md
    2026-03-23_09-11-02_fe5d4af5.md
  another-project/
    2026-03-20_17-30-00_308b6c72.md
```

## 요구 사항

- Python 3 (시스템 `PATH`에서 접근 가능해야 함)
- Claude Code 2.x 이상

## 설치

**1. 설치 스크립트 실행:**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/cadenzah/claude-conversation-logger/main/install.sh)
```

저장소가 `~/.claude/plugins/conversation-logger`에 클론됩니다. 같은 명령을 다시 실행하면 플러그인이 최신 버전으로 업데이트됩니다.

**2. Stop hook 등록** — `~/.claude/settings.json`에 아래 내용을 추가합니다:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/plugins/conversation-logger/hooks/save-conversation-log.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

`Stop` 하위에 이미 다른 훅이 있다면 해당 배열에 항목을 추가하면 됩니다.

다음 Claude Code 세션부터 플러그인이 동작합니다.

## 업데이트

동일한 설치 스크립트를 다시 실행하면 최신 변경사항을 반영합니다:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/cadenzah/claude-conversation-logger/main/install.sh)
```

## 로그 형식

각 파일은 세션 메타데이터로 시작하고, 이후 대화 내용이 이어집니다:

```markdown
# Conversation Log

- **Session ID**: `0024fc91-...`
- **Project**: `my-project` (`/Users/you/my-project`)
- **Started**: 2026-03-24 13:04:37
- **Last updated**: 2026-03-24 14:22:10
- **Messages**: 42

---

## User `2026-03-24 13:04:37`

Stop hook은 어떻게 설정하나요?

## Claude `2026-03-24 13:05:14`

<details>
<summary>Thinking</summary>

사용자가 Stop hook에 대해 묻고 있습니다...

</details>

Stop hook은 `~/.claude/settings.json`의 `"hooks"` 키 아래에 설정합니다...
```

## 프로젝트에서 로그에 빠르게 접근하기

프로젝트 디렉토리 안에 심볼릭 링크를 만들면 해당 프로젝트의 대화 로그에 바로 접근할 수 있습니다:

```bash
ln -s ~/.claude/conversation-logs/$(basename "$PWD") ./.claude/conversation-logs
```

이후 `.claude/conversation-logs/`가 해당 프로젝트의 모든 저장된 세션을 가리킵니다.

> **주의:** 심볼릭 링크를 `.gitignore`에 추가해 커밋되지 않도록 하세요. 대상 경로(`~/.claude/conversation-logs/`)는 로컬 환경에 종속되므로, 다른 사람의 환경에서는 링크가 깨집니다.
>
> ```bash
> echo ".claude/conversation-logs" >> .gitignore
> ```
>
> 심볼릭 링크를 제거하려면 그냥 삭제하면 됩니다 — 실제 로그 파일은 영향받지 않습니다:
>
> ```bash
> rm ./.claude/conversation-logs
> ```

## 동작 원리

플러그인은 Claude가 응답을 완료할 때마다 발동하는 `Stop` 훅을 등록합니다. 훅은 현재 세션의 JSONL 트랜스크립트 경로를 받아 파싱한 뒤 마크다운 파일로 씁니다. 매번 파일을 덮어쓰기 때문에 세션 중에도 항상 최신 스냅샷을 유지합니다.

## 기여

버그 리포트나 기능 요청은 이슈로, 코드 기여는 Pull Request로 언제든 환영합니다.

새로운 출력 형식, 필터링 옵션, 메타데이터 개선 등 아이디어가 있다면 편하게 참여해 주세요.

## 라이선스

MIT
