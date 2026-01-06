#!/bin/bash
# HLS 播放链路测试脚本

set -e

MODEM_API="http://127.0.0.1:8000"
NVR_DIRECT="http://192.168.99.11:8787"
CAMERA_IP="192.168.11.103"

echo "=== HLS 播放链路测试 ==="
echo ""

echo "1. 测试 live-hls API (main profile):"
echo "   GET ${MODEM_API}/v1/nvr/cameras/${CAMERA_IP}/live-hls?profile=main"
RESPONSE=$(curl -s "${MODEM_API}/v1/nvr/cameras/${CAMERA_IP}/live-hls?profile=main")
PLAYLIST=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('hls', {}).get('playlist', 'N/A'))" 2>/dev/null || echo "N/A")
PROFILE=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('hls', {}).get('profile', 'N/A'))" 2>/dev/null || echo "N/A")
echo "   Response: OK"
echo "   Playlist: $PLAYLIST"
echo "   Profile: $PROFILE"
echo ""

if [[ "$PLAYLIST" == *"http://"* ]]; then
    echo "   ⚠️  警告: playlist 是完整URL，应该是相对路径"
else
    echo "   ✅ playlist 是相对路径（正确）"
fi

if [[ "$PROFILE" == "main" ]]; then
    echo "   ✅ profile 参数正确传递"
else
    echo "   ⚠️  警告: profile 应该是 'main'，实际是 '$PROFILE'"
fi
echo ""

echo "2. 测试播放列表代理:"
if [[ "$PLAYLIST" == *"http://"* ]]; then
    PLAYLIST_PATH=$(echo "$PLAYLIST" | sed 's|http://[^/]*||')
else
    PLAYLIST_PATH="$PLAYLIST"
fi
echo "   GET ${MODEM_API}${PLAYLIST_PATH}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${MODEM_API}${PLAYLIST_PATH}")
if [[ "$HTTP_CODE" == "200" ]]; then
    echo "   ✅ 播放列表可访问 (HTTP $HTTP_CODE)"
    echo "   内容预览:"
    curl -s "${MODEM_API}${PLAYLIST_PATH}" | head -5 | sed 's/^/      /'
else
    echo "   ❌ 播放列表不可访问 (HTTP $HTTP_CODE)"
fi
echo ""

echo "3. 测试直接访问NVR (对比):"
echo "   GET ${NVR_DIRECT}/v1/cameras/${CAMERA_IP}/live-hls?profile=main"
NVR_RESPONSE=$(curl -s "${NVR_DIRECT}/v1/cameras/${CAMERA_IP}/live-hls?profile=main")
NVR_PLAYLIST=$(echo "$NVR_RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('hls', {}).get('playlist', 'N/A'))" 2>/dev/null || echo "N/A")
NVR_PROFILE=$(echo "$NVR_RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('hls', {}).get('profile', 'N/A'))" 2>/dev/null || echo "N/A")
echo "   NVR Playlist: $NVR_PLAYLIST"
echo "   NVR Profile: $NVR_PROFILE"
echo ""

echo "4. 测试NVR播放列表直接访问:"
echo "   GET ${NVR_DIRECT}${NVR_PLAYLIST}"
NVR_PLAYLIST_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${NVR_DIRECT}${NVR_PLAYLIST}")
if [[ "$NVR_PLAYLIST_CODE" == "200" ]]; then
    echo "   ✅ NVR 播放列表可访问 (HTTP $NVR_PLAYLIST_CODE)"
else
    echo "   ❌ NVR 播放列表不可访问 (HTTP $NVR_PLAYLIST_CODE)"
fi
echo ""

echo "=== 测试完成 ==="
echo ""
echo "建议："
echo "1. 如果 playlist 是完整URL，需要重启 modem-api 服务以加载新代码"
echo "2. 如果播放列表代理返回404，检查路由是否正确注册"
echo "3. 确保 App 使用相对路径访问播放列表，通过 modem-api 代理"

