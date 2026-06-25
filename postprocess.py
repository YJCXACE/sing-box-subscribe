"""
后处理脚本:
main.py 用 {Mitce} / {DJJC} 占位符生成的 config.json 里,有两个内部"节点池"
selector(🔖NodePool-Mitce / 🔖NodePool-DJJC),里面分别是各自订阅的真实节点tag。

这个脚本读取这两个池子,分别按节点tag前缀(HK/TW/JP/SG/US/KR)拆分成
该订阅专属的 urltest 地区组(例如 ♾️自动选择-Mitce-HK / ♾️自动选择-DJJC-HK),
插入回 config.json,然后把两个池子selector本身从最终配置里删掉
(它们只是中间数据,不需要出现在App的分组列表里)。

某个订阅在某个地区没有节点的话,会自动从所有 selector 的候选列表里
摘除对应tag的引用,避免悬空引用导致配置非法。
"""
import json
import re

CONFIG_PATH = "dist/config.json"

REGIONS = [
    ("HK", re.compile(r"^HK", re.IGNORECASE)),
    ("TW", re.compile(r"^TW", re.IGNORECASE)),
    ("JP", re.compile(r"^JP", re.IGNORECASE)),
    ("SG", re.compile(r"^SG", re.IGNORECASE)),
    ("US", re.compile(r"^US", re.IGNORECASE)),
    ("KR", re.compile(r"^KR", re.IGNORECASE)),
]

POOLS = [
    ("Mitce", "🔖NodePool-Mitce"),
    ("DJJC", "🔖NodePool-DJJC"),
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

    for pool_name, pool_tag in POOLS:
        pool_obj = by_tag.get(pool_tag)
        node_tags = pool_obj.get("outbounds", []) if pool_obj else []
        node_tags = [t for t in node_tags if t in by_tag and by_tag[t].get("type") not in (
            "selector", "urltest", "direct", "block")]

        for region, pattern in REGIONS:
            group_tag = f"♾️自动选择-{pool_name}-{region}"
            all_possible_tags.add(group_tag)
            matched = [t for t in node_tags if pattern.match(t)]
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

        print(f"{pool_name}: 共{len(node_tags)}个节点, "
              f"{[(r, len([t for t in node_tags if p.match(t)])) for r, p in REGIONS]}")

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

    config["outbounds"] = final_outbounds

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    print(f"生成的地区组: {sorted(valid_tags)}")
    if missing_tags:
        print(f"以下地区本次没有节点,已从选择器中摘除引用: {sorted(missing_tags)}")


if __name__ == "__main__":
    main()
