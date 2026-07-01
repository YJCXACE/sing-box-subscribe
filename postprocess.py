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
    import urllib.request
    import base64

    try:
        req = urllib.request.Request(sub_url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print("[patch_djjc] 拉取原始订阅失败: " + str(e))
        return config

    # 尝试base64解码,失败则当明文
    try:
        import base64 as _b64
        raw_clean = raw.strip().replace(b"\r", b"").replace(b"\n", b"").replace(b" ", b"")
        pad = 4 - len(raw_clean) % 4
        if pad != 4:
            raw_clean += b"=" * pad
        text = _b64.b64decode(raw_clean).decode("utf-8", errors="ignore")
    except Exception:
        text = raw.decode("utf-8", errors="ignore")

    print("[patch_djjc] 内容前80字符: " + repr(text[:80]))

    extra = {}
    # 格式1: hysteria2://...#名称 (URI格式)
    if "hysteria2://" in text:
        import urllib.parse as _up
        from urllib.parse import urlparse as _urlparse, parse_qs as _pqs
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("hysteria2://"):
                continue
            try:
                url = _urlparse(line)
                params = _pqs(url.query)
                name = _up.unquote(line.split("#")[-1]) if "#" in line else ""
                if not name or any(k in name for k in ["流量", "套餐", "到期", "剩余"]):
                    continue
                mport = params.get("mport", [None])[0]
                pin = params.get("pinSHA256", [None])[0]
                if mport or pin:
                    extra[name] = {"ports": mport, "fingerprint": pin}
            except Exception:
                continue
    else:
        # 格式2: Clash YAML (按"- name:"分割)
        for separator in ["\n  - name:", "\n- name:"]:
            if separator in text:
                proxy_blocks = text.split(separator)
                for block in proxy_blocks[1:]:
                    lines = block.split("\n")
                    name = lines[0].strip().strip("\"'")
                    ptype = ports = fingerprint = None
                    for ln in lines:
                        s = ln.strip()
                        if s.startswith("type:"):
                            ptype = s.split(":", 1)[1].strip().strip("\"'")
                        elif s.startswith("ports:"):
                            ports = s.split(":", 1)[1].strip().strip("\"'")
                        elif s.startswith("fingerprint:") and not fingerprint:
                            fingerprint = s.split(":", 1)[1].strip().strip("\"'")
                        elif s.startswith("ca-str:") and not fingerprint:
                            fingerprint = s.split(":", 1)[1].strip().strip("\"'")
                    if ptype == "hysteria2" and name and (ports or fingerprint):
                        extra[name] = {"ports": ports, "fingerprint": fingerprint}
                break

    print("[patch_djjc] 找到 " + str(len(extra)) + " 个DJJC Hysteria2节点的额外参数")
    if extra:
        print("[patch_djjc] 示例: " + str(list(extra.items())[:2]))

    patched = 0
    for o in config.get("outbounds", []):
        tag = o.get("tag", "")
        if o.get("type") != "hysteria2":
            continue
        matched_name = None
        for name in extra:
            if name in tag or tag in name:
                matched_name = name
                break
        if not matched_name:
            continue
        info = extra[matched_name]
        # server_ports/hop_interval 暂时跳过
        # pinSHA256在sing-box里没有对应字段,改为设置insecure=true跳过证书验证
        # 原理:原始节点用pinSHA256替代域名验证,sing-box不支持所以改用insecure
        if info["fingerprint"]:
            tls = o.setdefault("tls", {})
            tls["insecure"] = True
        patched += 1

    print("[patch_djjc] 成功补填 " + str(patched) + " 个节点")
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
            group_tag = "♾️自动选择-" + pool_name + "-" + region
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

        whole_pool_tag = "♾️自动选择-" + pool_name
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

        print(pool_name + ": 共" + str(len(node_tags)) + "个节点, " + str(matched_summary))

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

    sub_url_2 = os.environ.get("SUB_URL_2", "")
    if sub_url_2:
        config = patch_djjc_hysteria2(config, sub_url_2)
    else:
        print("[patch_djjc] SUB_URL_2未设置,跳过补填")

    # 读取自定义收藏网址列表,动态注入路由规则
    custom_domains_path = "custom_domains.txt"
    if os.path.exists(custom_domains_path):
        domains = []
        with open(custom_domains_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    domains.append(line)
        if domains:
            # 在路由规则最前面插入收藏网址规则(优先级最高)
            fav_rule = {
                "domain_suffix": domains,
                "action": "route",
                "outbound": "⭐收藏网址"
            }
            config["route"]["rules"].insert(0, fav_rule)
            print("[custom_domains] 注入 " + str(len(domains)) + " 个收藏域名: " + str(domains))
        else:
            print("[custom_domains] 列表为空,跳过注入")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    print("生成的地区组: " + str(sorted(valid_tags)))
    if missing_tags:
        print("以下地区本次没有节点,已从选择器中摘除引用: " + str(sorted(missing_tags)))


if __name__ == "__main__":
    main()
