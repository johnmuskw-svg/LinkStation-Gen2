#!/bin/bash
# ===== 二代上执行：恢复 App侧->NVR侧 的转发 + NAT（只管先通）=====
set -e

# 找到 NVR 那张网卡（192.168.99.x）
NVR_IF=$(ip -o -4 addr show | awk '$4 ~ /^192\.168\.99\./ {print $2; exit}')

# App/路由器侧：用默认路由网卡当作上游（一般是 wlan0/usb0/eth1 之类）
UP_IF=$(ip route | awk '/default/ {print $5; exit}')

echo "NVR_IF=$NVR_IF"
echo "UP_IF=$UP_IF"

# 没找到就直接报错，别继续瞎写规则
test -n "$NVR_IF"
test -n "$UP_IF"

# 开启转发
sudo sysctl -w net.ipv4.ip_forward=1

# 确保 nft 存在（没有就装）
command -v nft >/dev/null || (sudo apt-get update && sudo apt-get install -y nftables)

# 立刻生效：清空旧规则（你下午乱七八糟的东西一律清掉）
sudo nft -f - <<EOF
flush ruleset

table inet filter {
  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state established,related accept

    # App侧 -> NVR侧 放行
    iif "$UP_IF" oif "$NVR_IF" ip daddr 192.168.99.11 tcp dport 8787 accept

    # 反向回包放行（已在 ct state 放行，这里不写也行）
    iif "$NVR_IF" oif "$UP_IF" accept
  }
}

table ip nat {
  chain postrouting {
    type nat hook postrouting priority 100; policy accept;

    # App侧访问 192.168.99.0/24 时，源地址伪装成二代的 99 网段地址
    oif "$NVR_IF" ip daddr 192.168.99.0/24 masquerade
  }
}
EOF

echo "OK: Gen2 forwarding + NAT applied."
sudo nft list ruleset
