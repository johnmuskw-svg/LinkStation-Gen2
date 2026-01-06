#!/bin/bash
# 测试新添加的API路由

BASE_URL="http://192.168.71.48:8000/v1/ctrl"

# 检查是否有jq，如果没有则使用python格式化JSON
if command -v jq &> /dev/null; then
    JSON_FORMAT="jq ."
elif command -v python3 &> /dev/null; then
    JSON_FORMAT="python3 -m json.tool"
else
    JSON_FORMAT="cat"
fi

echo "=========================================="
echo "测试网络模式选择 API"
echo "=========================================="

echo -e "\n1. 测试 GET /ctrl/network_mode (查询网络模式)"
RESPONSE=$(curl -s "${BASE_URL}/network_mode" 2>&1)
if echo "$RESPONSE" | grep -q "Not Found"; then
    echo "❌ 404 Not Found - 应用需要重启"
else
    echo "✅ 请求成功:"
    echo "$RESPONSE" | $JSON_FORMAT
fi

echo -e "\n2. 测试 POST /ctrl/network_mode (dry_run模式)"
RESPONSE=$(curl -s -X POST "${BASE_URL}/network_mode" \
  -H "Content-Type: application/json" \
  -d '{"mode_pref":"LTE:NR5G","dry_run":true}' 2>&1)
if echo "$RESPONSE" | grep -q "Not Found"; then
    echo "❌ 404 Not Found - 应用需要重启"
else
    echo "✅ 请求成功:"
    echo "$RESPONSE" | $JSON_FORMAT
fi

echo -e "\n=========================================="
echo "测试频段偏好设置 API"
echo "=========================================="

echo -e "\n3. 测试 GET /ctrl/band_preference (查询频段偏好)"
RESPONSE=$(curl -s "${BASE_URL}/band_preference" 2>&1)
if echo "$RESPONSE" | grep -q "Not Found"; then
    echo "❌ 404 Not Found - 应用需要重启"
else
    echo "✅ 请求成功:"
    echo "$RESPONSE" | $JSON_FORMAT
fi

echo -e "\n4. 测试 POST /ctrl/band_preference (dry_run模式)"
RESPONSE=$(curl -s -X POST "${BASE_URL}/band_preference" \
  -H "Content-Type: application/json" \
  -d '{"lte_bands":[1,3,7],"nsa_nr5g_bands":[1,41,78],"dry_run":true}' 2>&1)
if echo "$RESPONSE" | grep -q "Not Found"; then
    echo "❌ 404 Not Found - 应用需要重启"
else
    echo "✅ 请求成功:"
    echo "$RESPONSE" | $JSON_FORMAT
fi

echo -e "\n=========================================="
echo "测试载波聚合 API (验证已更新为安全)"
echo "=========================================="

echo -e "\n5. 测试 POST /ctrl/ca (dry_run模式)"
RESPONSE=$(curl -s -X POST "${BASE_URL}/ca" \
  -H "Content-Type: application/json" \
  -d '{"lte_ca_enable":true,"nr_ca_enable":true,"dry_run":true}' 2>&1)
if echo "$RESPONSE" | grep -q "Not Found"; then
    echo "❌ 404 Not Found"
else
    echo "✅ 请求成功:"
    echo "$RESPONSE" | $JSON_FORMAT
    # 检查dangerous字段
    if echo "$RESPONSE" | grep -q '"dangerous":false'; then
        echo "✅ dangerous字段已正确设置为false（安全）"
    elif echo "$RESPONSE" | grep -q '"dangerous":true'; then
        echo "⚠️  dangerous字段仍为true（应用未重启，仍使用旧代码）"
    fi
fi

echo -e "\n=========================================="
echo "测试完成"
echo "=========================================="

