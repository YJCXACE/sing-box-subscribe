"""
后处理脚本:
main.py 用 {Mitce} / {DJJC} 占位符生成的 config.json 里,有两个内部"节点池"
selector(🔖NodePool-Mitce / 🔖NodePool-DJJC),里面分别是各自订阅的真实节点tag。

这个脚本读取这两个池子,各自按"地区识别规则"拆分成该订阅专属的 urltest
地区组(例如 ♾️自动选择-Mitce-HK / ♾️自动选择-DJJC-日本),插入回 config.json,
然后把两个池子selector本身从最终配置里删掉(纯中间数据,不需要出现在
App的分组列表里)。

两个订阅命名风格不同,所以各自配了一套匹配规则:
- Mitce: 英文地区前缀(HK-/TW-/JP-/SG-/US-/KR-)
- DJJC : 纯中文地区关键词(日本/美国/香港……),覆盖面更广

某个订阅在某个地区没有节点的话,会自动从所有 selector 的候选列表里
摘除对应tag的引用,避免悬空引用导致配置非法。
"""
import json
import re

CONFIG_PATH = "dist/config.json"

# Mitce: 英文前缀匹配
MITCE_REGIONS = [
    ("HK", re.compile(r"^HK", re.IGNORECASE)),
    ("TW", re.compile(r"^TW", re.IGNORECASE)),
    ("JP", re.compile(r"^JP", re.IGNORECASE)),
    ("SG", re.compile(r"^SG", re.IGNORECASE)),
    ("US", re.compile(r"^US", re.IGNORECASE)),
    ("KR", re.compile(r"^KR", re.IGNORECASE)),
]

# DJJC: 中文关键词匹配(re.search,关键词可以出现在名字任意位置)
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
    ("Mitce", "🔖NodePool-Mitce", MITCE_REGIONS),
    ("DJJC", "🔖NodePool-DJJC", DJJC_REGIONS),
]

URLTEST_URL = "https://www.gstatic.com/generate_204"
URLTEST_INTERVAL = "30m"
URLTEST_TOLERANCE = 30


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

        # 该订阅整体(不分地区)的自动选择组
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

    # 保险:不管什么原因导致同一个tag被重复添加,这里统一去重,只保留第一次出现的
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

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    print(f"生成的地区组: {sorted(valid_tags)}")
    if missing_tags:
        print(f"以下地区本次没有节点,已从选择器中摘除引用: {sorted(missing_tags)}")


if __name__ == "__main__":
    main()
