# filename: postprocess.py
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

# DJJC: 中文关键词匹配
DJJC_REGIONS = [
    ("香港", re.compile(r"香港|HK|HongKong")),
    ("台湾", re.compile(r"台湾|台北|TW|Taiwan")),
    ("日本", re.compile(r"日本|东京|大阪|京都|JP|Japan")),
    ("新加坡", re.compile(r"新加坡|狮城|SG|Singapore")),
    ("美国", re.compile(r"美国|纽约|洛杉矶|圣好塞|圣何塞|US|America|United States")),
    ("韩国", re.compile(r"韩国|首尔|KR|Korea")),
    ("德国", re.compile(r"德国|法兰克福|DE|Germany")),
    ("法国", re.compile(r"法国|巴黎|FR|France")),
    ("荷兰", re.compile(r"荷兰|阿姆斯特丹|NL|Netherlands")),
    ("俄罗斯", re.compile(r"俄罗斯|莫斯科|伯力|RU|Russia")),
    ("加拿大", re.compile(r"加拿大|枫叶|CA|Canada")),
    ("澳大利亚", re.compile(r"澳大利亚|悉尼|墨尔本|AU|Australia")),
    ("印度", re.compile(r"印度|孟买|IN|India")),
    ("巴西", re.compile(r"巴西|圣保罗|BR|Brazil")),
    ("墨西哥", re.compile(r"墨西哥|MX|Mexico")),
    ("南非", re.compile(r"南非|约翰内斯堡|ZA|South Africa")),
    ("迪拜", re.compile(r"迪拜|阿联酋|AE|Dubai")),
    ("瑞典", re.compile(r"瑞典|SE|Sweden")),
    ("瑞士", re.compile(r"瑞士|CH|Switzerland")),
    ("土耳其", re.compile(r"土耳其|伊斯坦布尔|TR|Turkey")),
    ("泰国", re.compile(r"泰国|曼谷|TH|Thailand")),
    ("菲律宾", re.compile(r"菲律宾|马尼拉|PH|Philippines")),
    ("印尼", re.compile(r"印尼|雅加达|ID|Indonesia")),
    ("越南", re.compile(r"越南|胡志明|VN|Vietnam")),
    ("马来西亚", re.compile(r"马来西亚|吉隆坡|MY|Malaysia")),
    ("阿根廷", re.compile(r"阿根廷|AR|Argentina")),
    ("意大利", re.compile(r"意大利|米兰|IT|Italy")),
    ("西班牙", re.compile(r"西班牙|马德里|ES|Spain")),
    ("波兰", re.compile(r"波兰|华沙|PL|Poland")),
]

POOLS = [
    ("Mitce", "🔖NodePool-Mitce", MITCE_REGIONS),
    ("DJJC", "🔖NodePool-DJJC", DJJC_REGIONS),
]

URLTEST_URL = "https://www.gstatic.com/generate_204"
URLTEST_INTERVAL = "3m0s"
URLTEST_TOLERANCE = 50

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def main():
    try:
        config = load_config()
    except FileNotFoundError:
        print(f"错误: 找不到 {CONFIG_PATH} 文件。请先确保生成了基础配置。")
        return

    outbounds = config.get("outbounds", [])
    
    # 建立快捷查找
    outbound_by_tag = {o["tag"]: o for o in outbounds if "tag" in o}

    # 收集模板定义的可能缺失的tag集合（即 `{all}` 展开的所有目标底层节点）
    all_possible_tags = set()
    for o in outbounds:
        if "outbounds" in o:
            for t in o["outbounds"]:
                if not t.startswith("🔖NodePool-") and t not in ["🌏️主代理", "Direct", "REJECT", "{all}"]:
                    all_possible_tags.add(t)

    valid_tags = set()
    new_region_outbounds = []

    # 遍历处理两个池子
    for pool_name, pool_tag, regions in POOLS:
        if pool_tag not in outbound_by_tag:
            print(f"警告: 在 outbounds 中找不到池子 {pool_tag}, 跳过该机场拆分。")
            continue

        pool_outbound = outbound_by_tag[pool_tag]
        node_tags = pool_outbound.get("outbounds", [])
        
        # 记录真实存在的节点
        valid_tags.update(node_tags)

        matched_summary = []
        for reg_name, regex in regions:
            matched = [t for t in node_tags if regex.search(t)]
            if matched:
                matched_summary.append(f"{reg_name}({len(matched)})")
                
                # 创建该机场专属的地区自动选择组
                new_region_outbounds.append({
                    "tag": f"♾️自动选择-{pool_name}-{reg_name}",
                    "type": "urltest",
                    "outbounds": matched,
                    "url": URLTEST_URL,
                    "interval": URLTEST_INTERVAL,
                    "tolerance": URLTEST_TOLERANCE,
                })

        print(f"{pool_name}: 共{len(node_tags)}个节点, 成功拆分区域: {', '.join(matched_summary) if matched_summary else '无'}")

    # 算出模板里定义了、但在实际节点列表里完全不存在的“缺失标签”
    missing_tags = all_possible_tags - valid_tags

    pool_tags = {p[1] for p in POOLS}
    final_outbounds = []
    
    # 🛡️ 强制白名单：收集所有合法、不能删除的非节点元素 🛡️
    protected_tags = {"🌏️主代理", "♾️自动选择", "♾️自动选择-Mitce", "♾️自动选择-DJJC", "Direct", "REJECT", "Proxy"}
    for o in new_region_outbounds:
        protected_tags.add(o.get("tag"))
    for o in outbounds:
        if o.get("tag") and (o["tag"].startswith("♾️自动选择") or o["tag"] == "🌏️主代理"):
            protected_tags.add(o["tag"])

    for o in outbounds:
        # 1. 过滤掉临时中转节点池 (🔖NodePool-*)
        if o.get("tag") in pool_tags:
            continue
        
        # 2. 清理选择器/测速组，剔除真正不存在的无效底层物理单节点，绝对放行策略组名
        if "outbounds" in o and missing_tags:
            o["outbounds"] = [
                t for t in o["outbounds"] 
                if t in protected_tags or (t not in missing_tags)
            ]
        final_outbounds.append(o)

    # 3. 将新生成的地区 urltest 子组插入到大总组 "♾️自动选择" 后面
    inserted = []
    for o in final_outbounds:
        inserted.append(o)
        if o.get("tag") == "♾️自动选择" and o.get("type") == "urltest":
            inserted.extend(new_region_outbounds)
    final_outbounds = inserted

    # 4. 极致风控：对相同 tag 进行规范性去重，保证顺序正确
    seen = set()
    deduped = []
    for o in final_outbounds:
        tag = o.get("tag")
        if not tag:
            continue
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(o)
    final_outbounds = deduped

    config["outbounds"] = final_outbounds

    # 5. 保存并导出最终配置
    save_config(config)
    print("✨ 后处理完成: 已成功整合并优化策略组分流架构，所有大组、小组及 fallback 链路闭环安全。")

if __name__ == "__main__":
    main()
