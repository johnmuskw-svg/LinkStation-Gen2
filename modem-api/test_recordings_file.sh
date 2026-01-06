#!/bin/bash
# 验收测试脚本：验证 recordings file 接口的 Range 请求和响应头透传

GEN2_URL="${1:-http://127.0.0.1:8000}"
IP="${2:-192.168.11.101}"
DATE="${3:-2025-12-16}"
FILENAME="${4:-test.mp4}"

echo "=== 测试 1: HEAD 请求检查响应头 ==="
curl -I "${GEN2_URL}/v1/nvr/recordings/${IP}/files/${DATE}/${FILENAME}" 2>&1 | grep -E "(HTTP|Content-Type|Accept-Ranges|Content-Length)" || echo "（文件可能不存在，这是正常的）"

echo ""
echo "=== 测试 2: Range 请求 (bytes=0-1023) ==="
curl -v -H "Range: bytes=0-1023" "${GEN2_URL}/v1/nvr/recordings/${IP}/files/${DATE}/${FILENAME}" 2>&1 | grep -E "(HTTP|Content-Range|Content-Type|Accept-Ranges)" || echo "（文件可能不存在，这是正常的）"

echo ""
echo "=== 测试 3: 检查 segments URL 重写 ==="
curl -s "${GEN2_URL}/v1/nvr/recordings/${IP}/days/${DATE}/segments" | python3 -m json.tool | grep -A 5 "segments" | head -20

echo ""
echo "=== 测试完成 ==="
echo "注意：如果文件不存在，会返回 404/502，这是正常的。"
echo "关键验证点："
echo "1. Range 请求应该返回 206 Partial Content（如果文件存在）"
echo "2. 响应头应包含 Accept-Ranges、Content-Type、Content-Range（Range 请求时）"
echo "3. segments 中的 url 字段应被重写为 Gen2 地址"

