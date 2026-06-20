"""
后处理脚本:
main.py 用 {all} 占位符生成的 config.json 只有一个全局的"自动选择"urltest组。
这个脚本在生成之后,按节点tag前缀(HK/TW/JP/SG/US/KR)把真实节点拆分成
若干个地区专属的 urltest 组,插入回 config.json,并保持选择器里
对这些地区组的引用是有效的(没有匹配到节点的地区会被自动从所有
selector 的候选列表里摘除,避免产生悬空引用导致配置非法)。
"""
import json
import re
import sys

CONFIG_PATH = "dist/config.json"

REGION_PATTERNS = [
    ("HK", re.compile(r"^HK", re.IGNORECASE)),
    ("TW", re.compile(r"^TW", re.IGNORECASE)),
    ("JP", re.compile(r"^JP", re.IGNORECASE)),
    ("SG", re.compile(r"^SG", re.IGNORECASE)),
    ("US", re.compile(r"^US", re.IGNORECASE)),
    ("KR", re.compile(r"^KR", re.IGNORECASE)),
]

NON_LEAF_TYPES = {"selector", "urltest", "direct", "block"}
URLTEST_URL = "https://www.gstatic.com/generate_204"
URLTEST_INTERVAL = "2m"
URLTEST_TOLERANCE = 30


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    outbounds = config.get("outbounds", [])

    leaf_tags = [
        o["tag"] for o in outbounds
        if o.get("type") not in NON_LEAF_TYPES and "tag" in o
    ]

    region_groups = {}
    for region, pattern in REGION_PATTERNS:
        matched = [tag for tag in leaf_tags if pattern.match(tag)]
        if matched:
            region_groups[region] = matched

    new_region_outbounds = []
    for region, tags in region_groups.items():
        new_region_outbounds.append({
            "tag": f"♾️自动选择-{region}",
            "type": "urltest",
            "outbounds": tags,
            "url": URLTEST_URL,
            "interval": URLTEST_INTERVAL,
            "tolerance": URLTEST_TOLERANCE,
        })

    # 找不到节点的地区,它们的占位tag要从所有selector里摘除,否则引用悬空
    all_region_tags = {f"♾️自动选择-{r}" for r, _ in REGION_PATTERNS}
    valid_region_tags = {f"♾️自动选择-{r}" for r in region_groups}
    missing_region_tags = all_region_tags - valid_region_tags

    for o in outbounds:
        if o.get("type") == "selector" and missing_region_tags:
            o["outbounds"] = [
                t for t in o["outbounds"] if t not in missing_region_tags
            ]

    # 把新的地区urltest组插入到全局"♾️自动选择"后面
    final_outbounds = []
    for o in outbounds:
        final_outbounds.append(o)
        if o.get("tag") == "♾️自动选择" and o.get("type") == "urltest":
            final_outbounds.extend(new_region_outbounds)

    config["outbounds"] = final_outbounds

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    print(f"按地区拆分完成: {[(r, len(t)) for r, t in region_groups.items()]}")
    if missing_region_tags:
        print(f"以下地区本次订阅没有节点,已从选择器中摘除引用: {missing_region_tags}")


if __name__ == "__main__":
    main()
