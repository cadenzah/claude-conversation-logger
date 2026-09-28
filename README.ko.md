# claude-conversation-logger

[English](README.md) | **한국어**

Claude Code 세션을 자동으로 읽기 좋은 마크다운 파일로 저장하는 플러그인입니다.

Claude가 응답을 완료할 때마다 현재 세션이 마크다운으로 디스크에 기록됩니다. 그대로 읽거나, grep으로 검색하거나, Obsidian 같은 노트 앱에서 열어볼 수 있습니다.

Claude Code도 `~/.claude/projects/`에 JSONL 원본 트랜스크립트를 남기지만, 사람이 읽기 어렵고 `cleanupPeriodDays`(기본 30일)가 지나면 삭제됩니다. 이 플러그인은 `/export` 없이도 읽기 좋은 사본을 자동으로, 영구히 보관합니다.

## 기능

- Claude 응답마다 세션을 `.md` 파일로 저장
- 프로젝트 이름별 하위 디렉토리로 정리
- 파일명에 세션 시작 시각과 사람이 읽기 좋은 제목 포함
- Extended thinking(`<details>` 블록)을 접을 수 있는 섹션으로 보존
- Claude Code 내부 시스템 태그는 제거하고 실제 대화만 저장

파일명의 제목은 Claude Code가 AI로 생성한 세션 제목을 우선 사용하며, 없을 경우 첫 번째 유의미한 사용자 메시지로 대체됩니다.

**로그 저장 위치:**
```
~/.claude/conversation-logs/
  my-project/
    2026-03-24_13-04-37_0024fc91_how-to-set-up-a-stop-hook.md
    2026-03-23_09-11-02_fe5d4af5_refactor-auth-middleware.md
  another-project/
    2026-03-20_17-30-00_308b6c72_initial-project-setup.md
```

## 요구 사항

- Python 3 (시스템 `PATH`에서 접근 가능해야 함)
- Claude Code 2.x 이상

## 설치

Claude Code 세션 안에서 실행합니다:

```
/plugin marketplace add cadenzah/claude-conversation-logger
/plugin install conversation-logger@cadenzah-plugins
```

셸에서 실행할 수도 있습니다:

```bash
claude plugin marketplace add cadenzah/claude-conversation-logger
claude plugin install conversation-logger@cadenzah-plugins
```

훅은 자동으로 등록되며(`settings.json` 수정 불필요) 백그라운드에서 실행되므로 Claude의 응답을 지연시키지 않습니다. 다음 세션부터, 또는 `/reload-plugins` 직후부터 동작합니다.

## 업데이트

```
/plugin marketplace update cadenzah-plugins
```

자동으로 업데이트를 받으려면 `/plugin` → **Marketplaces** → `cadenzah-plugins` → **Enable auto-update**를 선택하세요.

## 기존 설치 스크립트에서 이전하기

이전 버전은 `~/.claude/plugins/conversation-logger`에 저장소를 클론하고 `~/.claude/settings.json`에 `Stop` 훅을 직접 추가하는 방식이었습니다. 이 방식으로 설치했다면 플러그인을 설치하기 **전에** 기존 설정을 제거하세요. 그렇지 않으면 모든 세션이 두 번 기록됩니다:

1. `~/.claude/settings.json`에서 command가 `python3 ~/.claude/plugins/conversation-logger/hooks/save-conversation-log.py`인 `Stop` 훅 항목을 삭제합니다.
2. 기존 클론을 삭제합니다:
   ```bash
   rm -rf ~/.claude/plugins/conversation-logger
   ```
3. 위의 `/plugin` 방식으로 설치합니다.

`~/.claude/conversation-logs/`에 있는 기존 로그는 그대로 유지되며 계속 갱신됩니다.

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

이후 `.claude/conversation-logs/`가 해당 프로젝트의 모든 저장된 세션을 가리킵니다. 심볼릭 링크의 위치는 원하는 경로로 자유롭게 수정할 수 있습니다 — 링크 이름이나 위치는 무관합니다.

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
