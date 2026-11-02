#!/usr/bin/env bash
# M1 验收验证脚本：基座健康 → 配置 → 数据库 → 引擎启动 → 完整分析 → PDF 导出
# 用法: bash deploy/verify_m1.sh
# 可用环境变量: BASE_URL / QUERY / SEARCH_WAIT_MAX / REPORT_WAIT_MAX / PDF_OUT
set -u

BASE_URL="${BASE_URL:-http://localhost:5000}"
QUERY="${QUERY:-新能源汽车市场舆情分析}"
SEARCH_WAIT_MAX="${SEARCH_WAIT_MAX:-2400}"
REPORT_WAIT_MAX="${REPORT_WAIT_MAX:-5400}"
POLL_INTERVAL="${POLL_INTERVAL:-30}"
PDF_OUT="${PDF_OUT:-m1_final_report.pdf}"
DB_CONTAINER="${DB_CONTAINER:-bettafish-db}"

RESULTS=()
TASK_ID=""

pass() { RESULTS+=("PASS|$1"); echo "[PASS] $1"; }
fail() { RESULTS+=("FAIL|$1"); echo "[FAIL] $1"; }
info() { echo "[INFO] $1"; }

# 从 JSON 提取字段（避免依赖 jq）
json_field() {
  python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read() or '{}')
    v = d
    for k in '$1'.split('.'):
        v = v.get(k) if isinstance(v, dict) else None
        if v is None: break
    print('' if v is None else v)
except Exception:
    print('')
" <<< "$2"
}

elapsed_min() { echo "$(( (SECONDS - $1) / 60 ))m$(( (SECONDS - $1) % 60 ))s"; }

echo "=========================================="
echo " BettaFish M1 验收验证"
echo " 基座: $BASE_URL | 主题: $QUERY"
echo "=========================================="

# ---------- 1. 基座健康检查 ----------
info "1/7 检查基座 /api/status ..."
resp=$(curl -fsS --max-time 10 "$BASE_URL/api/status" 2>/dev/null)
if [ -n "$resp" ]; then pass "基座 API 可访问 ($BASE_URL/api/status)"; else fail "基座 API 不可访问，请确认容器已启动: docker compose -f deploy/docker-compose.m1.yml ps"; fi

# ---------- 2. 配置加载检查 ----------
info "2/7 检查 /api/config 配置加载 ..."
resp=$(curl -fsS --max-time 10 "$BASE_URL/api/config" 2>/dev/null)
success=$(json_field "success" "$resp")
cfg_count=$(json_field "config" "$resp" | python3 -c "import sys;print(len(sys.stdin.read().split(',')))" 2>/dev/null)
if [ "$success" = "True" ] || [ "$success" = "true" ]; then
  pass "配置加载成功（共 ${cfg_count} 项）"
else
  fail "配置加载失败（/api/config 返回异常），检查容器内 /app/.env 挂载"
fi

# ---------- 3. 数据库与 pgvector ----------
info "3/7 检查数据库与 pgvector 扩展 ..."
if docker exec "$DB_CONTAINER" pg_isready -U bettafish -d bettafish >/dev/null 2>&1; then
  pass "PostgreSQL 就绪（容器 $DB_CONTAINER）"
else
  fail "PostgreSQL 未就绪，检查 db 容器日志: docker logs $DB_CONTAINER"
fi
if docker exec "$DB_CONTAINER" psql -U bettafish -d bettafish -tAc "SELECT 1 FROM pg_extension WHERE extname='vector'" 2>/dev/null | grep -q 1; then
  pass "pgvector 扩展已启用"
else
  fail "pgvector 扩展未启用（若 db_data 为旧卷，需删除重建以触发 init_db.sql）"
fi

# ---------- 4. 启动三引擎 ----------
info "4/7 启动系统组件（Streamlit 引擎，可能需要 1-3 分钟）..."
resp=$(curl -fsS --max-time 900 -X POST "$BASE_URL/api/system/start" 2>/dev/null)
success=$(json_field "success" "$resp")
if [ "$success" = "True" ] || [ "$success" = "true" ]; then
  pass "三个引擎启动成功（insight/media/query，端口 8501-8503）"
else
  msg=$(json_field "message" "$resp")
  fail "引擎启动失败: $msg（查看 logs/ 与 docker logs bettafish）"
fi

# ---------- 5. 提交分析 ----------
info "5/7 提交分析请求: $QUERY"
resp=$(curl -fsS --max-time 60 -X POST -H "Content-Type: application/json" \
  -d "{\"query\": \"$QUERY\"}" "$BASE_URL/api/search" 2>/dev/null)
success=$(json_field "success" "$resp")
if [ "$success" = "True" ] || [ "$success" = "true" ]; then
  pass "分析请求已分发至引擎"
else
  msg=$(json_field "message" "$resp")
  fail "分析请求失败: $msg"
fi

# ---------- 6. 等待引擎产出并生成报告 ----------
info "6/7 等待引擎完成爬取分析并触发报告生成（最长 ${SEARCH_WAIT_MAX}s，每 ${POLL_INTERVAL}s 轮询）..."
T0=$SECONDS
ACCEPTED=0
while [ $((SECONDS - T0)) -lt "$SEARCH_WAIT_MAX" ]; do
  resp=$(curl -fsS --max-time 30 -X POST -H "Content-Type: application/json" \
    -d "{\"query\": \"$QUERY\"}" "$BASE_URL/api/report/generate" 2>/dev/null)
  success=$(json_field "success" "$resp")
  if [ "$success" = "True" ] || [ "$success" = "true" ]; then
    TASK_ID=$(json_field "task_id" "$resp")
    ACCEPTED=1
    pass "报告生成任务已接受: task_id=$TASK_ID"
    break
  fi
  echo "  ... 引擎尚未产出全部输入文件（已等待 $(elapsed_min T0)），继续等待"
  sleep "$POLL_INTERVAL"
done
if [ "$ACCEPTED" != "1" ]; then
  fail "超时仍未被接受（missing_files）：检查各 *_streamlit_reports/ 与 logs/，或调大 SEARCH_WAIT_MAX"
fi

info "等待报告生成完成（最长 ${REPORT_WAIT_MAX}s）..."
if [ "$ACCEPTED" = "1" ]; then
  T1=$SECONDS
  DONE=0
  while [ $((SECONDS - T1)) -lt "$REPORT_WAIT_MAX" ]; do
    resp=$(curl -fsS --max-time 30 "$BASE_URL/api/report/progress/$TASK_ID" 2>/dev/null)
    status=$(json_field "status" "$resp")
    progress=$(json_field "progress" "$resp")
    case "$status" in
      completed)
        DONE=1; pass "报告生成完成（耗时 $(elapsed_min T1)）"; break ;;
      error)
        fail "报告生成出错（查看 /api/report/log 或 logs/）"; break ;;
      *)
        echo "  ... 状态=$status 进度=${progress:-?}（已等待 $(elapsed_min T1)）"
        sleep "$POLL_INTERVAL" ;;
    esac
  done
  [ "$DONE" != "1" ] && [ "$status" != "error" ] && fail "报告生成超时（${REPORT_WAIT_MAX}s），可调大 REPORT_WAIT_MAX"
fi

# ---------- 7. 导出 PDF ----------
info "7/7 导出 PDF ..."
if [ -n "$TASK_ID" ]; then
  http=$(curl -sS --max-time 300 -o "$PDF_OUT" -w "%{http_code}" \
    "$BASE_URL/api/report/export/pdf/$TASK_ID" 2>/dev/null)
  size=$(stat -c%s "$PDF_OUT" 2>/dev/null || echo 0)
  if [ "$http" = "200" ] && [ "$size" -gt 100000 ]; then
    pass "PDF 导出成功: $PDF_OUT ($(( size / 1024 )) KB)"
  else
    fail "PDF 导出失败 (http=$http, size=${size}B)，检查 /api/report/log"
  fi
else
  fail "无 task_id，跳过 PDF 导出"
fi

# ---------- 汇总 ----------
echo "=========================================="
pass_n=$(printf '%s\n' "${RESULTS[@]}" | grep -c '^PASS' || true)
fail_n=$(printf '%s\n' "${RESULTS[@]}" | grep -c '^FAIL' || true)
printf '%s\n' "${RESULTS[@]}" | sed 's/|/  /'
echo "=========================================="
echo "结果: $pass_n 通过 / $fail_n 失败"
if [ "$fail_n" = "0" ]; then
  echo "M1 验收通过 ✔"
  exit 0
else
  echo "M1 验收未通过，请按 FAIL 项排查"
  exit 1
fi
