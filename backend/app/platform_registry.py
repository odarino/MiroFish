"""
平台注册表 (Platform Registry)

MiroFish 支持的社交平台的单一事实来源 (single source of truth)。

位置：app/platform_registry.py（刻意放在 services 包之外，避免 config 导入时
触发 services/__init__ 的重依赖，从而产生循环导入）。

历史上 twitter/reddit 的差异被硬编码在十多个文件里 (config、profile 生成、
config 生成、simulation_runner、run_parallel_simulation、report_agent、前端…)。
本模块把"平台"抽象成一份数据描述，其余代码遍历本注册表，而不是写
`if platform == "twitter" / elif "reddit"`。新增平台（如 Facebook）只需在此
登记一条 PlatformSpec，并在 OASIS fork 侧提供对应实现。

字段与 OASIS fork (odarino/oasis@feat/facebook) 对齐：
- oasis_platform_type 对应 `oasis.DefaultPlatformType.<X>.value`
- actions 为 `oasis.ActionType` 的成员名（字符串），脚本侧用
  `getattr(ActionType, name)` 还原
- graph_generator 为 `oasis` 顶层导出的 `generate_<X>_agent_graph`
"""

from dataclasses import dataclass, field
from typing import Dict, List


# ------------------------------------------------------------------
# 各平台的动作集（使用 oasis.ActionType 的成员名，字符串形式）
# ------------------------------------------------------------------
TWITTER_ACTIONS: List[str] = [
    "CREATE_POST", "LIKE_POST", "REPOST", "FOLLOW", "DO_NOTHING", "QUOTE_POST",
]

REDDIT_ACTIONS: List[str] = [
    "LIKE_POST", "DISLIKE_POST", "CREATE_POST", "CREATE_COMMENT",
    "LIKE_COMMENT", "DISLIKE_COMMENT", "SEARCH_POSTS", "SEARCH_USER",
    "TREND", "REFRESH", "DO_NOTHING", "FOLLOW", "MUTE",
]

# 与 fork 中 ActionType.get_default_facebook_actions() 保持一致
FACEBOOK_ACTIONS: List[str] = [
    "CREATE_POST", "REACT_POST", "CREATE_COMMENT", "LIKE_COMMENT",
    "SEND_FRIEND_REQUEST", "ACCEPT_FRIEND_REQUEST", "UNFRIEND",
    "CREATE_GROUP", "JOIN_GROUP", "LEAVE_GROUP", "REPORT_POST",
    "SEARCH_POSTS", "SEARCH_USER", "REFRESH", "DO_NOTHING",
]


@dataclass(frozen=True)
class PlatformSpec:
    """描述一个可模拟的社交平台。"""
    name: str                    # 内部标识："twitter" | "reddit" | "facebook"
    label: str                   # 展示名
    oasis_platform_type: str     # == oasis.DefaultPlatformType.<X>.value
    recsys_type: str             # == oasis.RecsysType.<X>.value
    profile_format: str          # "csv" | "json"
    profile_filename: str        # 落盘的 profile 文件名
    db_filename: str             # 该平台的 sqlite 数据库文件名
    graph_generator: str         # oasis 顶层的 generate_<X>_agent_graph 名称
    actions: List[str]           # ActionType 成员名列表
    use_boost: bool = False      # 是否优先用加速 LLM 配置（并行时错峰）
    enabled_by_default: bool = True


PLATFORMS: Dict[str, PlatformSpec] = {
    "twitter": PlatformSpec(
        name="twitter",
        label="Twitter/X",
        oasis_platform_type="twitter",
        recsys_type="twhin-bert",
        profile_format="csv",
        profile_filename="twitter_profiles.csv",
        db_filename="twitter_simulation.db",
        graph_generator="generate_twitter_agent_graph",
        actions=TWITTER_ACTIONS,
        use_boost=False,
    ),
    "reddit": PlatformSpec(
        name="reddit",
        label="Reddit",
        oasis_platform_type="reddit",
        recsys_type="reddit",
        profile_format="json",
        profile_filename="reddit_profiles.json",
        db_filename="reddit_simulation.db",
        graph_generator="generate_reddit_agent_graph",
        actions=REDDIT_ACTIONS,
        use_boost=True,
    ),
    "facebook": PlatformSpec(
        name="facebook",
        label="Facebook",
        oasis_platform_type="facebook",
        recsys_type="facebook",
        # Facebook 复用 reddit 风格的 JSON profile
        # (generate_facebook_agent_graph 读取 username/bio/persona[+demographics])
        profile_format="json",
        profile_filename="facebook_profiles.json",
        db_filename="facebook_simulation.db",
        graph_generator="generate_facebook_agent_graph",
        actions=FACEBOOK_ACTIONS,
        use_boost=False,
        # 需要 OASIS fork 支持；默认不启用，避免在未装 fork 时报错
        enabled_by_default=False,
    ),
}


def all_platforms() -> List[PlatformSpec]:
    """返回所有已登记的平台。"""
    return list(PLATFORMS.values())


def platform_names() -> List[str]:
    """返回所有平台的内部标识。"""
    return list(PLATFORMS.keys())


def get_platform(name: str) -> PlatformSpec:
    """按名称获取平台描述；未知平台抛 KeyError。"""
    return PLATFORMS[name]


def enabled_platforms() -> List[PlatformSpec]:
    """返回默认启用的平台。"""
    return [p for p in PLATFORMS.values() if p.enabled_by_default]


def resolve_actions(name: str):
    """把某平台的动作名解析为 oasis.ActionType 成员（供脚本侧使用）。

    仅在已安装 oasis 的进程（模拟子进程）中调用。
    """
    from oasis import ActionType
    return [getattr(ActionType, a) for a in get_platform(name).actions]
