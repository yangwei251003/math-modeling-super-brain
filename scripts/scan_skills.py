#!/usr/bin/env python3
"""
scan_skills.py — 扫描已安装 Skill 并识别数学建模相关子 Skill

用法：
    python scan_skills.py                          # 扫描所有 Skill
    python scan_skills.py --format markdown         # 以 Markdown 表格输出
    python scan_skills.py --format json             # 以 JSON 格式输出
    python scan_skills.py --all                     # 显示所有 Skill（含非建模）
"""

import os
import sys
import json
import re
import glob
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ============================================================
# 配置：数学建模各环节关键词
# ============================================================
CATEGORY_KEYWORDS = {
    "problem_analysis": {
        "label_cn": "问题分析",
        "keywords_cn": ["问题分析", "题目解析", "建模思路", "问题理解", "需求分析"],
        "keywords_en": ["problem analysis", "problem understanding", "question analysis"],
    },
    "data_collection": {
        "label_cn": "数据采集",
        "keywords_cn": ["数据采集", "爬虫", "数据获取", "数据收集", "网络爬取"],
        "keywords_en": ["data collection", "scraping", "crawler", "data acquisition"],
    },
    "data_preprocessing": {
        "label_cn": "数据预处理",
        "keywords_cn": ["数据清洗", "缺失值", "异常值", "归一化", "标准化", "数据预处理", "数据转换"],
        "keywords_en": ["data cleaning", "preprocessing", "normalization", "missing value", "outlier"],
    },
    "eda": {
        "label_cn": "探索性分析",
        "keywords_cn": ["探索性分析", "EDA", "描述统计", "数据探索", "相关性分析", "分布分析"],
        "keywords_en": ["exploratory", "eda", "descriptive statistics", "correlation"],
    },
    "statistical_analysis": {
        "label_cn": "统计分析",
        "keywords_cn": ["统计分析", "假设检验", "回归", "方差分析", "t检验", "卡方", "anova"],
        "keywords_en": ["statistics", "hypothesis test", "regression", "anova", "chi-square"],
    },
    "model_building": {
        "label_cn": "模型构建",
        "keywords_cn": ["模型构建", "建模", "预测", "分类", "聚类", "优化", "微分方程", "机器学习",
                        "深度学习", "神经网络", "时间序列", "规划", "决策"],
        "keywords_en": ["model", "prediction", "classification", "clustering", "optimization", "machine learning",
                        "neural network", "time series", "differential equation", "planning"],
    },
    "model_validation": {
        "label_cn": "模型验证",
        "keywords_cn": ["模型验证", "交叉验证", "灵敏度分析", "误差分析", "鲁棒性", "稳定性检验"],
        "keywords_en": ["validation", "cross validation", "sensitivity", "error analysis", "robustness"],
    },
    "visualization": {
        "label_cn": "数据可视化",
        "keywords_cn": ["可视化", "图表", "绘图", "画图", "数据图"],
        "keywords_en": ["visualization", "chart", "plot", "graph", "figure"],
    },
    "paper_writing": {
        "label_cn": "论文撰写",
        "keywords_cn": ["论文", "写作", "撰写", "latex", "摘要", "文献", "排版", "学术写作"],
        "keywords_en": ["paper", "writing", "latex", "abstract", "thesis", "academic writing"],
    },
    "format_check": {
        "label_cn": "格式检查",
        "keywords_cn": ["格式检查", "排版", "格式规范", "引用格式", "参考文献格式"],
        "keywords_en": ["format", "typesetting", "citation", "reference format"],
    },
    "compliance": {
        "label_cn": "合规审查",
        "keywords_cn": ["合规", "ai声明", "学术规范", "查重", "学术诚信"],
        "keywords_en": ["compliance", "ai declaration", "academic integrity", "plagiarism"],
    },
}

# 核心建模关键词（匹配到任何一个就算"建模相关"）
CORE_MODELING_KEYWORDS = [
    "建模", "数模", "数学建模", "mathematical model", "modeling competition",
    "mcm", "icm", "cumcm", "数学建模竞赛",
    "optimization", "prediction", "forecast", "data analysis",
    "统计分析", "统计测度", "机器学习", "machine learning",
    "数据处理", "数据清洗", "数据预处理",
    "论文撰写", "论文写作", "学术论文",
    "回归分析", "分类模型", "聚类分析", "时间序列",
    "灵敏度分析", "模型验证", "模型评估",
    "综合发展水平", "影响因素研究", "区域差异",
]

# 排除关键词（即使匹配了核心关键词，也要排除）
EXCLUDE_KEYWORDS = [
    "web animation", "动画设计", "css animation",
    "frontend", "ui design", "react component",
]


def parse_yaml_frontmatter(content: str) -> Dict[str, str]:
    """简易 YAML frontmatter 解析器，不依赖 pyyaml。"""
    if not content.startswith("---"):
        return {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    frontmatter = parts[1]
    result = {}

    # 解析简单的 key: value 行（支持多行值缩进）
    current_key = None
    current_value = ""

    for line in frontmatter.split("\n"):
        # 跳过空行和注释
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 检查是否是新的 key: value
        match = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', line)
        if match and not line.startswith(" "):
            # 保存上一个 key
            if current_key:
                result[current_key] = current_value.strip()

            current_key = match.group(1)
            current_value = match.group(2)
        elif current_key and (line.startswith("  ") or line.startswith("\t")):
            # 续行（缩进）
            current_value += " " + stripped
        elif current_key:
            # 非缩进且非 key: value 的行，结束上一个 key
            result[current_key] = current_value.strip()
            current_key = None
            current_value = ""

    # 保存最后一个 key
    if current_key:
        result[current_key] = current_value.strip()

    return result


def find_skills(base_paths: List[str]) -> List[Dict]:
    """扫描所有 Skill 目录，返回 Skill 信息列表。"""
    skills = []
    for base_path in base_paths:
        base = Path(base_path).expanduser().resolve()
        if not base.exists():
            continue
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            info = parse_skill_md(skill_md, str(skill_dir))
            if info:
                skills.append(info)
    return skills


def parse_skill_md(skill_md_path: Path, skill_dir: str) -> Optional[Dict]:
    """解析 SKILL.md 的 YAML 前置元数据。"""
    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except Exception:
        return None

    metadata = parse_yaml_frontmatter(content)
    if not metadata:
        return None

    name = metadata.get("name", skill_md_path.parent.name)
    description = metadata.get("description", "")

    return {
        "name": name,
        "description": str(description),
        "dir": skill_dir,
        "path": str(skill_md_path),
    }


def classify_skill(skill: Dict) -> List[str]:
    """根据 Skill 的 name 和 description 判断其属于哪些数学建模环节。"""
    text = (skill["name"] + " " + skill["description"]).lower()
    matched = set()

    for cat_key, cat_info in CATEGORY_KEYWORDS.items():
        for kw in cat_info["keywords_cn"]:
            if kw.lower() in text:
                matched.add(cat_info["label_cn"])
                break
        else:
            for kw in cat_info["keywords_en"]:
                if kw.lower() in text:
                    matched.add(cat_info["label_cn"])
                    break

    return sorted(matched)


def is_modeling_related(skill: Dict) -> bool:
    """判断 Skill 是否与数学建模核心领域相关。"""
    text = (skill["name"] + " " + skill["description"]).lower()

    # 先检查排除关键词
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return False

    for kw in CORE_MODELING_KEYWORDS:
        if kw.lower() in text:
            return True
    if classify_skill(skill):
        return True
    return False


def format_markdown(skills: List[Dict], only_related: bool = True) -> str:
    """以 Markdown 表格格式输出。"""
    if only_related:
        skills = [s for s in skills if is_modeling_related(s)]

    if not skills:
        return "未发现任何数学建模相关的子 Skill。"

    lines = ["## 已识别的数学建模子 Skill\n"]
    lines.append("| Skill 名称 | 适用环节 | 描述 | 路径 |")
    lines.append("|-----------|---------|------|------|")

    for s in skills:
        cats = classify_skill(s)
        cat_str = ", ".join(cats) if cats else "通用建模"
        desc_short = s["description"][:80].replace("\n", " ").replace("|", "|")
        name = s["name"].replace("|", "|")
        path = s["dir"].replace("|", "|")
        lines.append(f"| {name} | {cat_str} | {desc_short} | {path} |")

    lines.append("")
    lines.append(f"共发现 {len(skills)} 个建模相关 Skill。")
    return "\n".join(lines)


def format_json(skills: List[Dict], only_related: bool = True) -> str:
    """以 JSON 格式输出。"""
    if only_related:
        skills = [s for s in skills if is_modeling_related(s)]

    result = []
    for s in skills:
        result.append({
            "name": s["name"],
            "path": s["path"],
            "categories": classify_skill(s),
            "description": s["description"],
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import argparse

    parser = argparse.ArgumentParser(description="扫描已安装的数学建模相关 Skill")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown",
                        help="输出格式 (默认: markdown)")
    parser.add_argument("--all", action="store_true",
                        help="显示所有 Skill（包括非建模相关的）")
    parser.add_argument("--paths", nargs="+", default=None,
                        help="自定义扫描路径")
    args = parser.parse_args()

    # 默认扫描路径
    if args.paths:
        base_paths = args.paths
    else:
        home = str(Path.home())
        base_paths = [
            os.path.join(home, ".workbuddy", "skills"),
        ]

    skills = find_skills(base_paths)

    if args.format == "json":
        print(format_json(skills, only_related=not args.all))
    else:
        print(format_markdown(skills, only_related=not args.all))


if __name__ == "__main__":
    main()
