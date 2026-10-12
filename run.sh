#!/bin/bash
# 단골 자동화 패키지 1번 — 온라인 예약 + 고객 관리 시스템
# 사용법: bash run.sh  →  http://localhost:5004 (포트 충돌 시 자동으로 다음 빈 포트 사용)
set -e
cd "$(dirname "$0")"

PORT=5004
while (exec 3<>/dev/tcp/127.0.0.1/$PORT) 2>/dev/null; do
  exec 3>&- 3<&-
  PORT=$((PORT + 1))
  if [ "$PORT" -gt 5100 ]; then
    echo "사용 가능한 포트를 찾지 못했습니다 (5004~5100 전부 사용 중)."
    exit 1
  fi
done

if [ "$PORT" -ne 5004 ]; then
  echo "포트 5004가 사용 중이라 ${PORT}번 포트로 실행합니다."
fi

python3 -c "import app; app.init_db()" 2>/dev/null || python3 -c "import app; app.init_db()"

echo "----------------------------------------"
echo " 온라인 예약 + 고객 관리 시스템 실행 중"
echo " → 손님 화면: http://localhost:${PORT}/"
echo " → 사장님 화면: http://localhost:${PORT}/admin"
echo " 종료: Ctrl+C"
echo "----------------------------------------"
exec python3 app.py --port "$PORT"
