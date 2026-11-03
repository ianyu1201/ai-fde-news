#!/bin/zsh
cd "${0:A:h}" || exit 1
python3 news.py build || exit 1
expected_revision=$(python3 -c 'import news; print(news.server_revision())') || exit 1
if curl -fsS --max-time 2 http://127.0.0.1:8765/api/health 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("app")=="ianyu-ai-news" and d.get("revision")==sys.argv[1] and d.get("markdownDownload") else 1)' "$expected_revision" 2>/dev/null; then
  open 'http://127.0.0.1:8765/ai-news/'
  exit 0
fi
# Only replace this project's own obsolete preview, never an unrelated listener.
preview_pid=$(lsof -tiTCP:8765 -sTCP:LISTEN)
if [[ -n "$preview_pid" ]]; then
  preview_cwd=$(lsof -a -p "$preview_pid" -d cwd -Fn | sed -n 's/^n//p')
  preview_args=$(ps -p "$preview_pid" -o args=)
  if [[ "$preview_cwd" == "$PWD" && "$preview_args" == *"news.py serve"* ]]; then
    kill -TERM "$preview_pid" || exit 1
    for attempt in {1..30}; do
      kill -0 "$preview_pid" 2>/dev/null || break
      sleep 0.1
    done
  else
    print '8765 端口被其他程序占用，请先关闭占用程序。'
    exit 1
  fi
fi
python3 news.py serve --open-browser
