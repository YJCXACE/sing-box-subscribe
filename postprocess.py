import json
import re
import os

CONFIG_PATH = "dist/config.json"

REGIONS = [
    ("HK", re.compile(r"^HK", re.IGNORECASE)),
    ("TW", re.compile(r"^TW", re.IGNORECASE)),
    ("JP", re.compile(r"^JP", re.IGNORECASE)),
    ("SG", re.compile(r"^SG", re.IGNORECASE)),
    ("US", re.compile(r"^US", re.IGNORECASE)),
    ("KR", re.compile(r"^KR", re.IGNORECASE)),
]

DJJC_REGIONS = [
    ("香港", re.compile("香港")),
    ("台湾", re.compile("台湾")),
    ("日本", re.compile("日本")),
    ("韩国", re.compile("韩国")),
    ("新加坡", re.compile("新加坡")),
    ("美国", re.compile("美国")),
    ("英国", re.compile("英国")),
    ("德国", re.compile("德国")),
    ("法国", re.compile("法国")),
    ("荷兰", re.compile("荷兰")),
    ("俄罗斯", re.compile("俄罗斯")),
    ("加拿大", re.compile("加拿大")),
    ("澳大利亚", re.compile("澳大利亚|澳洲")),
    ("印度", re.compile("印度")),
    ("巴西", re.compile("巴西")),
    ("墨西哥", re.compile("墨西哥")),
    ("南非", re.compile("南非|非洲")),
    ("迪拜", re.compile("迪拜|阿联酋")),
    ("瑞典", re.compile("瑞典")),
    ("瑞士", re.compile("瑞士")),
    ("土耳其", re.compile("土耳其")),
    ("泰国", re.compile("泰国")),
    ("菲律宾", re.compile("菲律宾")),
    ("印尼", re.compile("印尼|印度尼西亚")),
    ("越南", re.compile("越南")),
    ("马来西亚", re.compile("马来西亚")),
    ("阿根廷", re.compile("阿根廷")),
    ("意大利", re.compile("意大利")),
    ("西班牙", re.compile("西班牙")),
    ("波兰", re.compile("波兰")),
]

POOLS = [
    ("Mitce", "🔖NodePool-Mitce", REGIONS),
    ("DJJC", "🔖NodePool-DJJC", DJJC_REGIONS),
]

URLTEST_URL = "https://www.gstatic.com/generate_204"
URLTEST_INTERVAL = "30m"
URLTEST_TOLERANCE = 30


def patch_djjc_hysteria2(config, sub_url):
    """
    DJJC订阅的Hysteria2节点在转换时丢失了两个关键参数:
    - mport (端口跳跃范围) -> sing-box的 server_ports 字段
    - pinSHA256 (证书指纹) -> sing-box的 tls.pinned_peer_certificate_chain_sha256
    """
    import urllib.request
    import urllib.parse
    import base64
    from urllib.parse import urlparse, parse_qs

    try:
        req = urllib.request.Request(sub_url, headers={"User-Agent": "clash.meta"})
        raw = urllib.request.urlopen(req, timeout=15).read()
        # 先尝试base64解码,失败则当明文直接用
        try:
            raw_clean = raw.strip().replace(b'\n', b'').replace(b'\r', b'').replace(b' ', b'')
            padding = 4 - len(raw_clean) % 4
            if padding != 4:
                raw_clean += b'=' * padding
            decoded = base64.b64decode(raw_clean).decode("utf-8")
        except Exception:
            decoded = raw.decode("utf-8", errors="ignore")
        print(f"[patch_djjc] 订阅内容前100字符: {decoded[:100]!r}")
    except Exception as e:
        print(f"[patch_djjc] 拉取原始订阅失败: {e}")
        return config

    extra = {}
    for line in decoded.split("\n"):
        line = line.strip()
        if not line.startswith("hysteria2://"):
            continue
        try:
            url = urlparse(line)
            params = parse_qs(url.query)
            name = urllib.parse.unquote(line.split("#")[-1]) if "#" in line else ""
            if not name or re.search(r"流量|套餐|到期", name):
                continue
            mport = params.get("mport", [None])[0]
            pin = params.get("pinSHA256", [None])[0]
            extra[name] = {"mport": mport, "pin": pin}
        except Exception:
            continue

    print(f"[patch_djjc] 找到 {len(extra)} 个DJJC Hysteria2节点的额外参数")

    patched = 0
    for o in config.get("outbounds", []):
        tag = o.get("tag", "")
        if o.get("type") != "hysteria2" or tag not in extra:
            continue
        info = extra[tag]
        if info["mport"] and "server_ports" not in o:
            o["server_ports"] = info["mport"]
            if "hop_interval" not in o:
                o["hop_interval"] = "30s"
            o.pop("server_port", None)
        if info["pin"]:
            tls = o.setdefault("tls", {})
            if "pinned_peer_certificate_chain_sha256" not in tls:
                try:
                    pin_b64 = base64.b64encode(bytes.fromhex(info["pin"])).decode()
                    tls["pinned_peer_certificate_chain_sha256"] = [pin_b64]
                except Exception:
                    pass
        patched += 1

    print(f"[patch_djjc] 成功补填 {patched} 个节点")
    return config


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    outbounds = config.get("outbounds", [])
    by_tag = {o["tag"]: o for o in outbounds if "tag" in o}

    new_region_outbounds = []
    all_possible_tags = set()
    valid_tags = set()

    for pool_name, pool_tag, regions in POOLS:
        pool_obj = by_tag.get(pool_tag)
        node_tags = pool_obj.get("outbounds", []) if pool_obj else []
        node_tags = [t for t in node_tags if t in by_tag and by_tag[t].get("type") not in (
            "selector", "urltest", "direct", "block")]

        matched_summary = []
        for region, pattern in regions:
            group_tag = f"♾️自动选择-{pool_name}-{region}"
            all_possible_tags.add(group_tag)
            matched = [t for t in node_tags if pattern.search(t)]
            matched_summary.append((region, len(matched)))
            if matched:
                valid_tags.add(group_tag)
                new_region_outbounds.append({
                    "tag": group_tag,
                    "type": "urltest",
                    "outbounds": matched,
                    "url": URLTEST_URL,
                    "interval": URLTEST_INTERVAL,
                    "tolerance": URLTEST_TOLERANCE,
                })

        whole_pool_tag = f"♾️自动选择-{pool_name}"
        all_possible_tags.add(whole_pool_tag)
        if node_tags:
            valid_tags.add(whole_pool_tag)
            new_region_outbounds.append({
                "tag": whole_pool_tag,
                "type": "urltest",
                "outbounds": node_tags,
                "url": URLTEST_URL,
                "interval": URLTEST_INTERVAL,
                "tolerance": URLTEST_TOLERANCE,
            })

        print(f"{pool_name}: 共{len(node_tags)}个节点, {matched_summary}")

    missing_tags = all_possible_tags - valid_tags

    pool_tags = {p[1] for p in POOLS}
    final_outbounds = []
    for o in outbounds:
        if o.get("tag") in pool_tags:
            continue
        if o.get("type") == "selector" and missing_tags:
            o["outbounds"] = [t for t in o["outbounds"] if t not in missing_tags]
        final_outbounds.append(o)

    inserted = []
    for o in final_outbounds:
        inserted.append(o)
        if o.get("tag") == "♾️自动选择" and o.get("type") == "urltest":
            inserted.extend(new_region_outbounds)
    final_outbounds = inserted

    # 去重保险
    seen = set()
    deduped = []
    for o in final_outbounds:
        tag = o.get("tag")
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(o)
    final_outbounds = deduped

    config["outbounds"] = final_outbounds

    # 补填DJJC订阅里被转换器丢失的Hysteria2关键参数
    sub_url_2 = os.environ.get("SUB_URL_2", "")
    if sub_url_2:
        config = patch_djjc_hysteria2(config, sub_url_2)
    else:
        print("[patch_djjc] SUB_URL_2未设置,跳过补填")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    print(f"生成的地区组: {sorted(valid_tags)}")
    if missing_tags:
        print(f"以下地区本次没有节点,已从选择器中摘除引用: {sorted(missing_tags)}")


if __name__ == "__main__":
    main()
