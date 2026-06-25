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
    
    # 1. 提取原始配置中所有合法的策略组 Tag 集合
    existing_group_tags = {o["tag"] for o in outbounds if "tag" in o}
    
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

    # 遍历处理两个池子并生成动态地区组
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

    # 将动态生成的地区组 Tag 名字也加入合法组集合中
    for o in new_region_outbounds:
        existing_group_tags.add(o["tag"])

    # 算出模板里定义了、但在实际节点列表里完全不存在的“缺失单节点标签”
    missing_tags = all_possible_tags - valid_tags

    pool_tags = {p[1] for p in POOLS}
    final_outbounds = []

    for o in outbounds:
        # 步骤 1: 剔除临时中转节点池 (🔖NodePool-*)
        if o.get("tag") in pool_tags:
            continue
        
        # 步骤 2: 精准清洗子节点列表
        if "outbounds" in o:
            clean_nodes = []
            for t in o["outbounds"]:
                # 核心风控逻辑：如果这个名字本身是一个策略组，或者它不属于缺失的失效节点列表，就绝对保留
                if t in existing_group_tags or t in ["Direct", "REJECT", "🌏️主代理", "♾️自动选择"]:
                    clean_nodes.append(t)
                elif t not in missing_tags:
                    clean_nodes.append(t)
            
            # 极致兜底：如果被洗成空列表了，强制放入 Direct 防止核心报错
            if not clean_nodes:
                clean_nodes = ["Direct"]
                
            o["outbounds"] = clean_nodes

        final_outbounds.append(o)

    # 步骤 3: 将新生成的地区 urltest 子组动态插入到大总组 "♾️自动选择" 后面
    inserted = []
    for o in final_outbounds:
        inserted.append(o)
        if o.get("tag") == "♾️自动选择" and o.get("type") == "urltest":
            inserted.extend(new_region_outbounds)
    final_outbounds = inserted

    # 步骤 4: 对相同 tag 进行全局去重，保护核心平稳加载
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
    print("✨ 后处理完成: 已成功整合并优化策略组分流架构，动态地区组与回退链路完美闭环。")

if __name__ == "__main__":
    main()
