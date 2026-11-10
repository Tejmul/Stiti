#!/bin/bash
# Run every Stiti eval against a fresh throwaway database (never the real brain).
set -euo pipefail
cd "$(dirname "$0")/.."
PG="${PG_BIN:-/opt/homebrew/opt/postgresql@18/bin}"
export STITI_DB="postgresql:///stiti_test"
export STITI_HOME="${STITI_TEST_HOME:-$(mktemp -d)}"
export STITI_EVENTKIT=off           # tests never create real Apple Reminders
fresh_db() {
  "$PG/dropdb" --if-exists stiti_test
  "$PG/createdb" stiti_test
  "$PG/psql" -q -v ON_ERROR_STOP=1 stiti_test -f db/schema.sql >/dev/null
  for m in db/migrations/*.sql; do "$PG/psql" -q -v ON_ERROR_STOP=1 stiti_test -f "$m" >/dev/null; done
}
fail=0
run() {
  name="$1"; shift
  if [ "${FRESH:-1}" = "1" ]; then fresh_db; fi
  if out=$(uv run python "$@" 2>&1); then echo "✅ $name — $(echo "$out" | tail -1)"; else echo "❌ $name"; echo "$out" | tail -20; fail=1; fi
}
run "dates (Hinglish time parsing)"   tests/dates_eval.py
run "recall (hybrid memory search)"   tests/recall_eval.py
run "memory (LongMemEval-style)"      tests/memory_eval.py
run "two-way USER/LESSONS sync"       tests/mdsync_eval.py
run "proactivity"                     tests/proactive_eval.py
run "learning loops"                  tests/learning_eval.py
run "whiteboard tutor"                tests/tutor_eval.py
run "web app (chat + security)"       tests/web_eval.py
run "conversation speed pieces"       tests/speed_eval.py
run "crash course + any book"         tests/course_eval.py
run "alarms, reminders, timers"       tests/alarms_eval.py
run "live internet info"            tests/live_eval.py
run "Hinglish voice (TTS)"          tests/hinglish_eval.py
run "conversation basics"           tests/conversation_eval.py
run "persona + psychology (D25)"   tests/persona_eval.py
exit $fail
