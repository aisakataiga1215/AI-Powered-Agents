"""SearchService: web search → candidate URL list for CollectorAgent.

Fires industry-keyed queries against a SearchProvider, filters unsupported
URLs, deduplicates, and returns up to _SEARCH_MAX_URLS candidates.
Tavily title/snippet are used for discovery only — never stored as evidence.
"""

import ipaddress
import re
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.services.search_provider import SearchProvider

logger = get_logger(__name__)

_SEARCH_MAX_URLS: int = 5

_QUERY_TEMPLATES: dict[str, list[str]] = {
    "ai_saas": [
        "{name} official pricing plans",
        "{name} official documentation",
        "{name} features overview",
        "{name} official help",
    ],
    "ai_search": [
        "{name} official pricing plans",
        "{name} product features",
        "{name} API documentation",
        "{name} official help center",
    ],
    "design_tools": [
        "{name} official pricing plans",
        "{name} product features",
        "{name} templates official",
        "{name} enterprise security",
    ],
    "ecommerce": [
        "{name} seller fees official",
        "{name} store subscription fees",
        "{name} return policy",
        "{name} buyer protection policy",
    ],
    "local_services": [
        "{name} driver partner program",
        "{name} delivery fees",
        "{name} official help",
    ],
    "open_source": [
        "{name} official about mission",
        "{name} documentation",
        "{name} foundation membership",
        "{name} donate support",
    ],
    "social": [
        "{name} advertising business",
        "{name} creator monetization",
        "{name} official help",
    ],
    "general": [
        "{name} official pricing",
        "{name} product features",
        "{name} official help",
    ],
}

# M15A: goal-aware query templates for interactive source search
_GOAL_QUERY_TEMPLATES: dict[str, list[str]] = {
    "pricing_analysis": ["{name} official pricing plans", "{name} pricing page"],
    "feature_comparison": ["{name} features overview", "{name} product features"],
    "user_personas": ["{name} documentation", "{name} how it works"],
    "swot": ["{name} official website", "{name} about company"],
}

_DEFAULT_SOURCE_QUERIES: list[str] = [
    "{name} official pricing",
    "{name} features",
    "{name} documentation",
    "{name} official website",
]

# Lower value = higher priority in sorted CandidateSource results
_SOURCE_TYPE_PRIORITY: dict[str, int] = {
    "official_website": 0,
    "pricing_page": 1,
    "docs": 2,
    "features_page": 3,
    "security": 4,
    "privacy": 5,
    "blog": 6,
    "news": 7,
    "review": 8,
    "manual_input": 9,
    "unknown": 10,
}

_UNSUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".mp4", ".avi", ".mov", ".mp3",
})

_BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com",
    "facebook.com", "fb.com", "tiktok.com",
    # reddit.com blocked in M14 — community/review source support is tracked for a future milestone
    "reddit.com",
    "linkedin.com",  # auth wall makes crawling unreliable
    "bit.ly", "t.co", "goo.gl", "tinyurl.com",
})

_ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_BLOCKED_HOSTS: frozenset[str] = frozenset({"localhost", "metadata.google.internal"})

# M16.2: known AI coding product domains — used to boost relevance score for confirmed products
_AI_CODING_PRODUCT_DOMAINS: frozenset[str] = frozenset({
    "cursor.com", "github.com",  # Cursor, GitHub Copilot
    "claude.ai", "anthropic.com",  # Claude Code
    "openai.com",  # Codex / ChatGPT
    "trae.ai",  # Trae
    "windsurf.com", "windsurf.ai", "codeium.com",  # Windsurf / Codeium
    "tabnine.com",  # Tabnine
    "qodo.ai",  # Qodo
    "replit.com",  # Replit
    "aws.amazon.com",  # Amazon Q Developer
    "jetbrains.com",  # JetBrains AI
    "sourcegraph.com",  # Sourcegraph Cody
    "continue.dev",  # Continue
    "devin.ai", "cognition.ai",  # Devin
})

# M16.2: negative topic terms for ambiguous brand names (e.g. Windsurf = sport vs IDE)
_BRAND_NEGATIVE_TERMS: frozenset[str] = frozenset({
    "windsurfing", "surf", "sailing", "board", "kite", "weather",
    "sport", "openearth", "watersport", "kiteboarding",
})
_AI_CODING_POSITIVE_TERMS: frozenset[str] = frozenset({
    "ai", "coding", "code", "developer", "ide", "editor", "programming",
    "copilot", "assistant", "llm", "autocomplete",
})

_AI_CODING_PRODUCTS: tuple[tuple[str, str, str], ...] = (
    ("Cursor", "https://cursor.com", "cursor.com"),
    ("GitHub Copilot", "https://github.com/features/copilot", "github.com"),
    ("Tabnine", "https://www.tabnine.com", "tabnine.com"),
    ("Qodo", "https://www.qodo.ai", "qodo.ai"),
    ("Windsurf", "https://windsurf.ai", "windsurf.ai"),
    ("Trae", "https://www.trae.ai", "trae.ai"),
    ("Replit", "https://replit.com", "replit.com"),
    ("Claude Code", "https://claude.ai/code", "claude.ai"),
    ("Codex", "https://openai.com/codex", "openai.com"),
    ("Amazon Q Developer", "https://aws.amazon.com/q/developer/", "aws.amazon.com"),
)

_KNOWN_PRODUCTS_BY_INDUSTRY: dict[str, tuple[tuple[str, str, str], ...]] = {
    "ai_saas": _AI_CODING_PRODUCTS,
    "ai_search": (
        ("Perplexity", "https://www.perplexity.ai", "perplexity.ai"),
        ("ChatGPT", "https://chatgpt.com", "chatgpt.com"),
        ("Claude", "https://claude.ai", "claude.ai"),
        ("Gemini", "https://gemini.google.com", "gemini.google.com"),
        ("Microsoft Copilot", "https://copilot.microsoft.com", "copilot.microsoft.com"),
        ("You.com", "https://you.com", "you.com"),
    ),
    "design_tools": (
        ("Canva", "https://www.canva.com", "canva.com"),
        ("Figma", "https://www.figma.com", "figma.com"),
        ("Adobe Express", "https://www.adobe.com/express", "adobe.com"),
        ("Sketch", "https://www.sketch.com", "sketch.com"),
        ("Framer", "https://www.framer.com", "framer.com"),
        ("Miro", "https://miro.com", "miro.com"),
    ),
    "ecommerce": (
        ("Amazon", "https://www.amazon.com", "amazon.com"),
        ("eBay", "https://www.ebay.com", "ebay.com"),
        ("Etsy", "https://www.etsy.com", "etsy.com"),
        ("JD.com", "https://www.jd.com", "jd.com"),
        ("Taobao", "https://www.taobao.com", "taobao.com"),
        ("Pinduoduo", "https://www.pinduoduo.com", "pinduoduo.com"),
        ("Walmart Marketplace", "https://marketplace.walmart.com", "walmart.com"),
        ("AliExpress", "https://www.aliexpress.com", "aliexpress.com"),
        ("Mercado Libre", "https://www.mercadolibre.com", "mercadolibre.com"),
    ),
    "local_services": (
        ("DoorDash", "https://www.doordash.com", "doordash.com"),
        ("Uber Eats", "https://www.ubereats.com", "ubereats.com"),
        ("Grubhub", "https://www.grubhub.com", "grubhub.com"),
        ("Meituan", "https://www.meituan.com", "meituan.com"),
        ("Ele.me", "https://www.ele.me", "ele.me"),
        ("Deliveroo", "https://deliveroo.com", "deliveroo.com"),
        ("Just Eat", "https://www.just-eat.com", "just-eat.com"),
        ("Instacart", "https://www.instacart.com", "instacart.com"),
    ),
    "social": (
        ("Tinder", "https://tinder.com", "tinder.com"),
        ("Bumble", "https://bumble.com", "bumble.com"),
        ("Hinge", "https://hinge.co", "hinge.co"),
        ("Badoo", "https://badoo.com", "badoo.com"),
        ("OkCupid", "https://www.okcupid.com", "okcupid.com"),
        ("Grindr", "https://www.grindr.com", "grindr.com"),
    ),
    "general": (
        ("Asana", "https://asana.com", "asana.com"),
        ("Trello", "https://trello.com", "trello.com"),
        ("monday.com", "https://monday.com", "monday.com"),
        ("ClickUp", "https://clickup.com", "clickup.com"),
        ("Jira", "https://www.atlassian.com/software/jira", "atlassian.com"),
        ("Notion", "https://www.notion.com", "notion.com"),
        ("Basecamp", "https://basecamp.com", "basecamp.com"),
        ("Smartsheet", "https://www.smartsheet.com", "smartsheet.com"),
    ),
    "open_source": (
        ("Wikipedia", "https://www.wikipedia.org", "wikipedia.org"),
        ("Mozilla", "https://www.mozilla.org", "mozilla.org"),
        ("Linux Foundation", "https://www.linuxfoundation.org", "linuxfoundation.org"),
    ),
}

_INDUSTRY_NEGATIVE_NAME_TERMS: dict[str, tuple[str, ...]] = {
    "ecommerce": (
        "store builder", "website builder", "create online store",
        "development", "negozio online",
    ),
    "local_services": ("software solution", "data & intelligence", "development", "white label"),
    "social": ("development", "builder", "app builder", "development company", "clone"),
    "ai_search": ("seo agency", "marketing agency", "search optimization"),
    "design_tools": ("design agency", "template marketplace", "course"),
}

_INDUSTRY_NEGATIVE_DOMAINS: dict[str, tuple[str, ...]] = {
    "ecommerce": ("godaddy.com",),
    "local_services": ("cloudflare.com", "github.com"),
    "ai_search": ("acquia.com",),
    "open_source": ("stradley.com",),
}

# M16.2: known product domain aliases for source_search official-domain priority
# Maps normalized competitor name → list of authoritative domains
_PRODUCT_DOMAIN_ALIASES: dict[str, list[str]] = {
    "windsurf": ["windsurf.ai", "windsurf.com", "docs.windsurf.com"],
    "cursor": ["cursor.com", "docs.cursor.com"],
    "trae": ["trae.ai", "docs.trae.ai"],
    "codeium": ["codeium.com", "windsurf.ai"],
    "copilot": ["github.com"],
    "github copilot": ["github.com"],
    "claude code": ["claude.ai", "anthropic.com"],
    "devin": ["devin.ai", "cognition.ai"],
    "tabnine": ["tabnine.com"],
    "replit": ["replit.com"],
    "qodo": ["qodo.ai"],
    "perplexity": ["perplexity.ai"],
    "chatgpt": ["chatgpt.com", "openai.com"],
    "claude": ["claude.ai", "anthropic.com"],
    "canva": ["canva.com"],
    "figma": ["figma.com"],
    "adobe express": ["adobe.com"],
    "wikipedia": ["wikipedia.org"],
    "mozilla": ["mozilla.org"],
    "linux foundation": ["linuxfoundation.org"],
    "amazon": ["amazon.com"],
    "ebay": ["ebay.com"],
    "etsy": ["etsy.com"],
    "doordash": ["doordash.com"],
    "uber eats": ["ubereats.com"],
    "instacart": ["instacart.com"],
    "meituan": ["meituan.com"],
    "饿了么": ["ele.me"],
    "ele.me": ["ele.me"],
    "京东": ["jd.com"],
    "淘宝": ["taobao.com"],
    "拼多多": ["pinduoduo.com"],
    "通义灵码": ["lingma.aliyun.com"],
    "豆包 marscode": ["marscode.com"],
    "marscode": ["marscode.com"],
}

# M15B: discovery-specific blocked domains (aggregators/listings/news, not competitors)
# Do NOT add DigitalOcean or Zapier here — they are valid competitors in cloud/automation
# industries. Their article/blog pages are handled by _ARTICLE_PATH_RE instead.
_DISCOVERY_BLOCKED_DOMAINS: frozenset[str] = frozenset({
    # Aggregator / listing / review sites
    "g2.com", "capterra.com", "producthunt.com", "alternativeto.net",
    "getapp.com", "softwareadvice.com", "trustradius.com",
    # Reference / encyclopedia
    "wikipedia.org", "crunchbase.com",
    # Analyst / research firms (not software products)
    "gartner.com", "forrester.com", "idc.com",
    # News / tech media
    "techcrunch.com", "venturebeat.com", "wired.com", "theverge.com",
    "zdnet.com", "cnet.com", "tomsguide.com", "pcmag.com",
    "infoq.com", "thenewstack.io", "spectrum.ieee.org", "mashable.com",
    "businessofapps.com", "elitedaily.com", "bonappetit.com",
    "statista.com", "similarweb.com",
    # Developer blogging platforms
    "hackernoon.com", "dev.to", "hashnode.dev", "dzone.com",
    # Social / community
    "reddit.com", "twitter.com", "linkedin.com", "medium.com", "substack.com",
    "virtina.com", "goodhousekeeping.com", "ebsco.com", "apps.apple.com",
    "play.google.com", "travelwithwildlynorth.com",
    "sohu.com", "news.qq.com", "tmtpost.com", "woshipm.com", "lfppt.com",
    "yuntingai.com", "xda-developers.com",
    # M16.3: dictionary, translation, encyclopedia, Q&A platforms — generic
    # content hosts that match any conversational prompt. Never a competitor.
    "youdao.com", "dict.cn", "iciba.com",
    "baike.baidu.com", "zhidao.baidu.com", "wenku.baidu.com", "tieba.baidu.com",
    "translate.google.com",
})

_DISCOVERY_RESEARCH_DOMAIN_KEYWORDS: tuple[str, ...] = (
    "research", "intelligence", "market", "markets", "mordor", "kbv",
    "straits", "report", "reports", "insights", "analytics", "analyst",
)

_DISCOVERY_PUBLISHER_PATH_RE = re.compile(
    r'/(?:[^/]*(?:best|top|guide|guides|review|reviews|comparison|comparisons|'
    r'compare|alternatives?|roundup|market-size|market-share|market-research|'
    r'market-report|industry-report|reports?|research|statistics|stats|data)[^/]*)'
    r'(?:/|$)|/(?:story|insights|article|articles|blog)(?:/|$)',
    re.IGNORECASE,
)

_LISTICLE_TITLE_RE = re.compile(
    r'^\s*(best|top\s*\d*|alternatives?(\s+to)?|comparison|compare|vs\.?|'
    r'review|list\s+of|\d+\s+(best|top)|guide|complete\s+guide|'
    r'full\s+comparison|i\s+tested|how\s+to|market\s+size|market\s+share|'
    r'market\s+research|industry\s+report|statistics|stats)',
    re.IGNORECASE,
)

# M16.2: also catch titles that END with listicle keywords
# e.g. "AI Coding Tools Comparison", "Best AI IDEs Review", "Windsurf vs Cursor"
_LISTICLE_TITLE_END_RE = re.compile(
    r'(?:^|\s)(?:comparison|compare|review|reviews|vs\.?|guide|alternatives?|'
    r'ranking|roundup|overview|tutorial|rundown|analysis|summary|platforms|'
    r'best\s+.*|top\s+.*)\s*$',
    re.IGNORECASE,
)

_CHINESE_DISCOVERY_CONTENT_TITLE_RE = re.compile(
    r"(竞品分析|产品分析|分析报告|主流.*app|ppt|模板|案例|教程|方法论|"
    r"必看|手把手|旧王与新王|新闻|资讯)",
    re.IGNORECASE,
)

# M16.1: article/blog/resource URL path patterns — these pages are content, not products
_ARTICLE_PATH_RE = re.compile(
    r'/(?:blog|article|articles|post|posts|news|guide|guides|resource|resources|'
    r'content|community|tutorial|tutorials|comparison|comparisons|compare|review|reviews|'
    r'glossary|learn|learning|knowledge|press|media)/',
    re.IGNORECASE,
)

# M16.1: TLD/domain patterns that are blogging platforms, not product companies
_BLOG_DOMAIN_RE = re.compile(r'\.blog$|\.ghost\.io$', re.IGNORECASE)

# M16.1/M16.2: minimum relevance_score to include in discover_competitors() results
# Raised to 60 in M16.2 to filter marginal candidates more aggressively
_DISCOVERY_MIN_SCORE: int = 60

_TITLE_STRIP_RE = re.compile(
    r'\s*[\|—\-–]\s*(home|official|pricing|docs?|documentation|overview|'
    r'features?|product|platform|company|inc\.?|llc|ltd|corp\.?|blog|login|'
    r'sign\s*up|get\s*started|try\s*free).*$',
    re.IGNORECASE,
)

_DISCOVERY_TEMPLATES: dict[str, list[str]] = {
    "ai_saas": [
        "{industry} competitors",
        "AI coding tools competitors",
        "AI IDE alternatives",
        "developer AI coding assistants",
    ],
    "ai_search": [
        "{industry} answer engine official",
        "{industry} AI search official",
        "{industry} chat assistant official",
        "Perplexity ChatGPT Claude official websites",
    ],
    "design_tools": [
        "{industry} design tool official",
        "{industry} creative platform official",
        "{industry} visual design software official",
        "Canva Figma Adobe Express official websites",
    ],
    "ecommerce": [
        "{industry} official ecommerce platform",
        "{industry} SaaS platform official",
        "{industry} online store builder official",
    ],
    "local_services": [
        "{industry} official app platform",
        "{industry} service companies official",
        "{industry} marketplace platform official",
    ],
    "open_source": [
        "{industry} foundation official",
        "{industry} nonprofit project official",
        "{industry} documentation community official",
    ],
    "social": [
        "{industry} app official website",
        "{industry} creator platform official",
        "{industry} social network official",
        "dating app official website",
        "Tinder Bumble Hinge official websites",
    ],
    "general": [
        "{industry} official software",
        "{industry} SaaS platform official",
        "{industry} tools official website",
        "{industry} competitors",
    ],
}

_DEFAULT_DISCOVERY_QUERIES: list[str] = [
    "{industry} competitors",
    "best {industry} tools",
    "{industry} alternatives",
]

_MAX_DISCOVERY_RESULTS: int = 12

# M16.3: NL-prompt → industry_type detection. The NL discovery panel does not
# send industry_type; backend infers it from the free-text prompt so the search
# templates and known-product extraction match the user's actual intent.
# Earlier entries take priority on ties (ecommerce/local_services/etc. before
# the generic AI categories so "AI 电商 工具" is classified as ecommerce, not ai_saas).
_INDUSTRY_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ecommerce", (
        "电商", "电子商务", "网店", "网购", "电销", "卖货", "带货",
        "跨境电商", "shopify", "marketplace", "ecommerce", "e-commerce",
        "online shop", "online store", "online retail", "merchant platform",
        "seller platform",
    )),
    ("local_services", (
        "本地生活", "外卖", "配送", "跑腿", "上门", "到家", "送餐",
        "打车", "网约车", "同城",
        "food delivery", "local service", "local services", "on-demand",
        "on demand", "ride sharing", "ride-hailing", "grocery delivery",
        "last mile",
    )),
    ("design_tools", (
        "设计工具", "设计软件", "设计平台", "平面设计", "ui设计",
        "原型工具", "原型设计",
        "design tool", "design tools", "design platform", "graphic design",
        "ui/ux", "ui design", "prototyping tool", "canva", "figma",
    )),
    ("ai_search", (
        "ai搜索", "智能搜索", "答案引擎", "ai问答", "ai 问答", "ai助手",
        "ai 助手", "智能问答",
        "ai search", "answer engine", "ai chatbot", "ai assistant",
        "perplexity",
    )),
    ("open_source", (
        "开源", "开源项目", "开源软件", "非营利", "非盈利", "基金会",
        "open source", "open-source", "nonprofit", "foundation", "oss project",
    )),
    ("social", (
        "社交", "约会", "交友", "婚恋", "陌生人社交", "兴趣社区",
        "dating", "matchmaking", "social network", "social app",
        "community app",
    )),
    ("ai_saas", (
        "ai 编程", "ai编程", "ai 代码", "ai代码", "ai ide", "编程助手",
        "代码助手", "代码补全",
        "ai coding", "code completion", "code assistant", "coding assistant",
        "developer ai", "ai copilot",
    )),
)


def _detect_industry_type(industry_text: str) -> str | None:
    """Detect industry_type from a free-text industry/prompt input.

    Scans for industry-specific keywords (Chinese + English). Returns the first
    matched industry_type per _INDUSTRY_KEYWORD_RULES order or None if no clear
    signal — callers should fall back to their explicit industry_type in that
    case.
    """
    if not industry_text:
        return None
    lower = industry_text.lower()
    for industry_type, keywords in _INDUSTRY_KEYWORD_RULES:
        if any(kw in lower for kw in keywords):
            return industry_type
    return None


# M16.3: Static English discovery queries keyed by industry_type. Used when an
# industry is confidently detected from the user's prompt. Avoids leaking
# Chinese conversational fragments into Tavily queries (which previously
# matched dict.youdao.com lookups and SEO ad pages).
_STATIC_DISCOVERY_QUERIES: dict[str, list[str]] = {
    "ai_saas": [
        "AI coding tool competitors",
        "AI IDE alternatives",
        "best AI code assistant",
        "developer AI coding assistants",
    ],
    "ai_search": [
        "AI search engine competitors",
        "AI answer engine alternatives",
        "best AI chat assistant",
        "Perplexity ChatGPT Claude alternatives",
    ],
    "design_tools": [
        "design tool competitors",
        "graphic design platform alternatives",
        "best design software",
        "Canva Figma Adobe Express alternatives",
    ],
    "ecommerce": [
        "ecommerce platform competitors",
        "online marketplace alternatives",
        "best ecommerce platform",
        "Amazon eBay Etsy Taobao competitors",
    ],
    "local_services": [
        "food delivery app competitors",
        "on-demand delivery platform alternatives",
        "local services marketplace",
        "DoorDash Uber Eats Meituan competitors",
    ],
    "open_source": [
        "open source project alternatives",
        "open source foundation",
        "nonprofit OSS organizations",
    ],
    "social": [
        "dating app competitors",
        "social network alternatives",
        "Tinder Bumble Hinge competitors",
    ],
}

_PRODUCT_DISCOVERY_ALIASES: dict[str, tuple[str, str]] = {
    "qq": ("QQ", "social"),
    "腾讯qq": ("QQ", "social"),
    "wechat": ("WeChat", "social"),
    "微信": ("WeChat", "social"),
    "telegram": ("Telegram", "social"),
    "discord": ("Discord", "social"),
    "whatsapp": ("WhatsApp", "social"),
    "line": ("LINE", "social"),
    "signal": ("Signal", "social"),
    "snapchat": ("Snapchat", "social"),
    "messenger": ("Messenger", "social"),
    "facebook messenger": ("Messenger", "social"),
    "微博": ("Weibo", "social"),
    "weibo": ("Weibo", "social"),
    "twitter": ("Twitter/X", "social"),
    "x": ("Twitter/X", "social"),
    "facebook": ("Facebook", "social"),
    "zepeto": ("ZEPETO", "social"),
    "vyou": ("Vyou", "social"),
    "星偶": ("星偶", "social"),
    "抖音": ("Douyin", "social"),
    "douyin": ("Douyin", "social"),
    "快手": ("Kuaishou", "social"),
    "kuaishou": ("Kuaishou", "social"),
    "b站": ("Bilibili", "social"),
    "哔哩哔哩": ("Bilibili", "social"),
    "bilibili": ("Bilibili", "social"),
}

_PRODUCT_COMPETITOR_SEEDS: dict[str, tuple[tuple[str, str, str, str, str], ...]] = {
    "qq": (
        ("WeChat", "https://www.wechat.com", "wechat.com", "direct_competitor", "IM social product with similar messaging and relationship-chain use cases."),
        ("WhatsApp", "https://www.whatsapp.com", "whatsapp.com", "direct_competitor", "Large-scale messaging product with similar communication jobs."),
        ("Messenger", "https://www.messenger.com", "messenger.com", "direct_competitor", "Messaging product connected to a large social graph."),
        ("Weibo", "https://weibo.com", "weibo.com", "indirect_competitor", "Text/image social network competing for communication and social attention."),
        ("Twitter/X", "https://x.com", "x.com", "indirect_competitor", "Public social feed model worth comparing for content and relationship mechanics."),
        ("Facebook", "https://www.facebook.com", "facebook.com", "indirect_competitor", "Social graph and feed product with adjacent user attention use cases."),
        ("ZEPETO", "https://zepeto.me", "zepeto.me", "inspiration_product", "Avatar social product useful for virtual identity and social-play mechanics."),
        ("Vyou", "https://www.vyou.com", "vyou.com", "inspiration_product", "Avatar/virtual social reference product."),
        ("星偶", "https://www.xingouapp.com", "xingouapp.com", "inspiration_product", "Avatar social reference product for virtual identity."),
        ("Douyin", "https://www.douyin.com", "douyin.com", "inspiration_product", "Video social/content product useful for retention and content loop inspiration."),
        ("Kuaishou", "https://www.kuaishou.com", "kuaishou.com", "inspiration_product", "Video community product useful for creator/community mechanics."),
        ("Bilibili", "https://www.bilibili.com", "bilibili.com", "inspiration_product", "Video/community product useful for interest-community operations."),
    ),
    "wechat": (
        ("QQ", "https://im.qq.com", "im.qq.com", "direct_competitor", "Tencent IM product with adjacent communication and social graph use cases."),
        ("Telegram", "https://telegram.org", "telegram.org", "direct_competitor", "Messaging product with channels/groups and cross-platform usage."),
        ("WhatsApp", "https://www.whatsapp.com", "whatsapp.com", "direct_competitor", "Large-scale messaging product with similar communication jobs."),
        ("LINE", "https://line.me", "line.me", "direct_competitor", "Messaging product with stickers, services, and social extensions."),
        ("Signal", "https://signal.org", "signal.org", "indirect_competitor", "Privacy-led messaging product worth comparing on trust and security."),
        ("Discord", "https://discord.com", "discord.com", "indirect_competitor", "Community/chat product for group and interest-based social use cases."),
    ),
}


def _extract_product_discovery_target(text: str) -> tuple[str, str, str] | None:
    """Return (alias_key, display_name, inferred_industry_type) for known products."""
    lower = (text or "").lower()
    for alias, (display_name, inferred_industry) in _PRODUCT_DISCOVERY_ALIASES.items():
        alias_lower = alias.lower()
        if alias_lower in {"qq", "腾讯qq", "微信"}:
            matched = alias_lower in lower
        else:
            matched = bool(re.search(rf"(?<![a-z0-9-]){re.escape(alias_lower)}(?![a-z0-9-])", lower))
        if matched:
            key = "wechat" if alias in {"微信", "wechat"} else alias.lower()
            if key == "腾讯qq":
                key = "qq"
            return key, display_name, inferred_industry
    return None


def _extract_generic_product_target(text: str) -> tuple[str, str, str] | None:
    """Extract an arbitrary product name from a product-competitor prompt."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return None
    patterns = (
        r"^(?:请|麻烦)?帮我分析一下\s*(.+?)\s*的竞品[。.!！?？]*$",
        r"^(?:请|麻烦)?帮我分析\s*(.+?)\s*的竞品[。.!！?？]*$",
        r"^(?:请|麻烦)?帮我看看\s*(.+?)\s*的竞品[。.!！?？]*$",
        r"^分析一下\s*(.+?)\s*的竞品[。.!！?？]*$",
        r"^分析\s*(.+?)\s*的竞品[。.!！?？]*$",
        r"^(.+?)\s*的竞品[。.!！?？]*$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned, flags=re.IGNORECASE)
        if match and match.group(1).strip():
            product = match.group(1).strip(" 「」\"'“”")
            if 1 < len(product) <= 60:
                return product.lower(), product, "general"
    return None


def _product_discovery_queries(display_name: str, alias_key: str) -> list[str]:
    if alias_key in {"qq", "wechat"}:
        return [
            f"{display_name} competitors official messaging apps",
            f"{display_name} alternatives chat apps",
            "QQ WeChat Telegram Discord WhatsApp LINE Signal official",
            "instant messaging app competitors official websites",
        ]
    return [
        f"{display_name} competitors official",
        f"{display_name} alternatives official",
        f"apps like {display_name} official websites",
    ]

# M16.3: Chinese conversational filler patterns. When a candidate name contains
# any of these the result is almost certainly from a translation/lookup page
# that matched the user's prompt verbatim, not an actual product.
_PROMPT_FILLER_PATTERNS: frozenset[str] = frozenset({
    "帮我", "请帮", "麻烦", "我想了解", "我想知道", "我想做",
    "分析一下", "看一下", "推荐一下",
    "竞品", "竞争对手", "对标", "类似产品",
    "怎么样", "有哪些", "求推荐",
})


def _extract_company_name(raw_title: str, url: str) -> str:
    """Heuristic: strip trailing suffixes from Tavily title, fall back to domain."""
    if raw_title and not _LISTICLE_TITLE_RE.match(raw_title):
        cleaned = _TITLE_STRIP_RE.sub("", raw_title).strip(" -–—|")
        first_segment = re.split(r"\s*[|—–]\s*", cleaned, maxsplit=1)[0].strip(" -–—|")
        if 2 <= len(first_segment) <= 60:
            return first_segment
        if 2 <= len(cleaned) <= 60:
            return cleaned
    domain = urlparse(url).netloc.removeprefix("www.")
    return domain.split(".")[0].title()


def _score_competitor_relevance(
    name: str, raw_title: str, url: str, domain: str, query: str,
    industry_type: str = "general",
) -> tuple[int, str]:
    """Return (score 0-100, reason). Lower scores indicate likely non-competitors."""
    # Hard disqualifications
    if any(domain == d or domain.endswith("." + d) for d in _DISCOVERY_BLOCKED_DOMAINS):
        return 0, "aggregator or listing site"
    # M16.3: candidate name contains the user's conversational prompt fragment
    # (e.g. 【帮我分析一下】 from dict.youdao.com) — this is never a real product.
    name_lower = name.lower()
    title_lower = raw_title.lower()
    if any(filler in name_lower or filler in title_lower for filler in _PROMPT_FILLER_PATTERNS):
        return 0, f"name contains conversational prompt filler: {name!r}"
    negative_domains = _INDUSTRY_NEGATIVE_DOMAINS.get(industry_type, ())
    if any(domain == d or domain.endswith("." + d) for d in negative_domains):
        return 20, f"domain is not a direct {industry_type} competitor: {domain}"
    if domain.startswith("blog.") or _BLOG_DOMAIN_RE.search(domain):
        return 5, f"blogging platform domain: {domain}"
    if any(keyword in domain for keyword in _DISCOVERY_RESEARCH_DOMAIN_KEYWORDS):
        return 10, f"domain looks like research or publisher: {domain}"
    parsed_path = urlparse(url).path.lower()
    if _LISTICLE_TITLE_RE.match(raw_title):
        return 15, f"title looks like a listicle: {raw_title[:60]!r}"
    if _CHINESE_DISCOVERY_CONTENT_TITLE_RE.search(raw_title):
        return 15, f"title looks like Chinese content/research article: {raw_title[:60]!r}"
    if _LISTICLE_TITLE_RE.search(raw_title):
        return 20, f"title contains listicle marker: {raw_title[:60]!r}"
    if _LISTICLE_TITLE_END_RE.search(raw_title):
        return 15, f"title ends with listicle keyword: {raw_title[:60]!r}"
    if _LISTICLE_TITLE_RE.match(name):
        return 10, f"extracted name looks like a list title: {name!r}"
    if _DISCOVERY_PUBLISHER_PATH_RE.search(parsed_path):
        return 20, f"URL path looks like publisher/research content: {parsed_path[:60]!r}"
    negative_name_terms = _INDUSTRY_NEGATIVE_NAME_TERMS.get(industry_type, ())
    combined_name = f"{name} {raw_title}".lower()
    if any(term in combined_name for term in negative_name_terms):
        return 25, f"name looks like a vendor/service provider, not a competitor: {name!r}"

    score = 50

    # M16.2: known AI coding product domains get a strong boost
    # BUT: only applies if the URL is on that domain's root or a product page,
    # not a deep path within a multi-project repo host (e.g. github.com/openearth/windsurf)
    is_known_ai_product = any(
        domain == d or domain.endswith("." + d) for d in _AI_CODING_PRODUCT_DOMAINS
    )
    # github.com is a known product domain, but individual repos are NOT the product itself.
    # Apply boost only for root paths or single-segment paths like /features/copilot.
    if is_known_ai_product and industry_type == "ai_saas":
        parsed_path_for_boost = urlparse(url).path.lower()
        path_segs_for_boost = [p for p in parsed_path_for_boost.strip("/").split("/") if p]
        # github.com: only boost for /features/* paths (e.g. GitHub Copilot), not user repos
        if domain == "github.com" and (
            len(path_segs_for_boost) >= 2 and path_segs_for_boost[0] != "features"
        ):
            is_known_ai_product = False  # Deep repo path — not the product itself
        else:
            score += 25

    # Domain quality (small signal — many non-products also use .com)
    if domain.endswith((".com", ".io", ".ai", ".co")):
        score += 5

    # Homepage depth: root path is the strongest signal it's a product homepage
    path_segments = [p for p in parsed_path.strip("/").split("/") if p]
    if len(path_segments) == 0:
        score += 15  # root homepage

    # Query keyword relevance
    first_word = query.split()[0].lower() if query.split() else ""
    if first_word and (first_word in name.lower() or first_word in domain):
        score += 20

    # Short, clean name
    if 2 <= len(name) <= 25:
        score += 5

    # M16.2: brand negative-term penalty — if snippet/title dominated by sport/non-tech
    # terms and no AI/coding signals present, cap score
    combined_text = (raw_title + " " + name).lower()
    has_negative = any(neg in combined_text for neg in _BRAND_NEGATIVE_TERMS)
    has_positive = any(
        re.search(rf"(?<![\w-]){re.escape(pos)}(?![\w-])", combined_text)
        for pos in _AI_CODING_POSITIVE_TERMS
    )
    if has_negative and not has_positive and not is_known_ai_product:
        score = min(score, 35)
        return min(score, 35), f"brand name matches non-tech topic: {name!r}"

    # Article/blog/resource URL path → hard cap regardless of other signals
    if _ARTICLE_PATH_RE.search(parsed_path):
        return min(score, 30), f"URL path looks like an article or blog: {parsed_path[:60]!r}"

    return min(score, 100), "appears to be a product/company"


def _is_blocked_host(hostname: str) -> bool:
    host = hostname.strip().lower().removeprefix("www.")
    if not host or host in _BLOCKED_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any((
        ip.is_private,
        ip.is_loopback,
        ip.is_link_local,
        ip.is_multicast,
        ip.is_reserved,
        ip.is_unspecified,
    ))


def _is_crawlable(url: str) -> bool:
    """Return False for unsupported, blocked, or unsafe crawl targets."""
    parsed = urlparse(url.lower())
    if parsed.scheme not in _ALLOWED_URL_SCHEMES or _is_blocked_host(parsed.hostname or ""):
        return False
    if any(parsed.path.endswith(ext) for ext in _UNSUPPORTED_EXTENSIONS):
        return False
    netloc = parsed.netloc.removeprefix("www.")
    if any(netloc == d or netloc.endswith("." + d) for d in _BLOCKED_DOMAINS):
        return False
    return True


def _normalize_url(url: str) -> str:
    """Simple normalization for internal deduplication of search results."""
    return url.rstrip("/").lower()


def _domain_matches(candidate_domain: str, allowed_domain: str) -> bool:
    # Candidate-source search uses explicit authoritative domains. Treat aliases
    # like docs.cursor.com as official only when listed, so community or forum
    # subdomains do not become high-confidence evidence by accident.
    return candidate_domain == allowed_domain


def _official_domains_for(competitor_name: str, competitor_website: str) -> list[str]:
    """Return authoritative domains for a competitor, preserving user-provided site."""
    domains: list[str] = []
    parsed_website = urlparse(competitor_website).netloc.removeprefix("www.").lower()
    if parsed_website:
        domains.append(parsed_website)

    aliases = _PRODUCT_DOMAIN_ALIASES.get(competitor_name.strip().lower(), [])
    for domain in aliases:
        normalized = domain.removeprefix("www.").lower()
        if normalized not in domains:
            domains.append(normalized)
    return domains


def _is_official_url(url: str, official_domains: list[str]) -> bool:
    domain = urlparse(url).netloc.removeprefix("www.").lower()
    return any(_domain_matches(domain, official) for official in official_domains)


def _infer_source_confidence(
    source_type: str,
    url: str,
    competitor_website: str,
    official_domains: list[str] | None = None,
) -> str:
    """Return 'high'/'medium'/'low' based on domain match and source type.

    M16.2: A source is only 'on_official' if its domain matches the competitor's
    own domain or known alias domain. Third-party docs/review hosts are never high.
    """
    domain = urlparse(url).netloc.removeprefix("www.").lower()
    comp_domain = urlparse(competitor_website).netloc.removeprefix("www.").lower()

    # Exact or subdomain match against the declared competitor website
    authoritative_domains = official_domains or [comp_domain]
    on_official = any(_domain_matches(domain, official) for official in authoritative_domains if official)

    # M16.2: exclude known third-party hosting platforms from being marked official
    from app.services.source_classifier import _THIRD_PARTY_HOSTING_DOMAINS
    if any(domain == d or domain.endswith("." + d) for d in _THIRD_PARTY_HOSTING_DOMAINS):
        on_official = False

    if on_official and source_type in {"official_website", "pricing_page", "docs"}:
        return "high"
    if on_official:
        return "medium"
    if source_type in {"review", "unknown"}:
        return "low"
    return "medium"


def _infer_source_reason(source_type: str, url: str) -> str:
    labels = {
        "pricing_page": "Pricing page",
        "official_website": "Official website",
        "docs": "Documentation",
        "features_page": "Features page",
        "security": "Security page",
        "privacy": "Privacy policy",
        "blog": "Blog post",
        "review": "Review or community mention",
        "news": "News article",
    }
    return labels.get(source_type, f"Web page at {urlparse(url).netloc}")


def _extract_known_ai_products(text: str) -> list[tuple[str, str, str]]:
    """Extract known AI coding products mentioned in listicle/search snippets."""
    return _extract_known_products(text, "ai_saas")


def _extract_known_products(text: str, industry_type: str) -> list[tuple[str, str, str]]:
    """Extract known products for an industry from listicle/search snippets."""
    found: list[tuple[str, str, str]] = []
    lower = text.lower()
    for name, website, domain in _KNOWN_PRODUCTS_BY_INDUSTRY.get(industry_type, ()):
        name_lower = name.lower()
        compact = name_lower.replace("github ", "")
        if re.search(rf"(?<![\w-]){re.escape(name_lower)}(?![\w-])", lower) or (
            compact != name_lower and re.search(rf"(?<![\w-]){re.escape(compact)}(?![\w-])", lower)
        ):
            found.append((name, website, domain))
    return found


class SearchService:
    def __init__(self, provider: SearchProvider) -> None:
        self._provider = provider

    def discover_urls(
        self,
        competitor_name: str,
        competitor_url: str,
        industry_type: str = "general",
        max_per_query: int = 3,
    ) -> list[str]:
        """Fire industry-keyed queries, filter, deduplicate, return up to _SEARCH_MAX_URLS URLs."""
        templates = _QUERY_TEMPLATES.get(industry_type, _QUERY_TEMPLATES["general"])
        seen: set[str] = set()
        result: list[str] = []

        for template in templates:
            query = template.format(name=competitor_name)
            try:
                hits = self._provider.search(query, max_results=max_per_query)
            except Exception as exc:
                logger.warning("SearchService: query '%s' failed: %s", query, exc)
                continue

            for hit in hits:
                if not _is_crawlable(hit.url):
                    continue
                norm = _normalize_url(hit.url)
                if norm in seen:
                    continue
                seen.add(norm)
                result.append(hit.url)
                if len(result) >= _SEARCH_MAX_URLS:
                    return result

        return result

    def search_sources(
        self,
        competitor_name: str,
        website: str,
        goals: list[str],
        industry_type: str = "general",
        max_per_query: int = 3,
    ) -> list["CandidateSource"]:
        """Return CandidateSource[] for user selection. Snippet = display-only hint, never stored.

        M16.2: Two-pass search strategy:
        1. First pass: include_domains=[official domain + aliases] for high-quality official sources.
        2. Second pass: full web search (no domain filter) for additional coverage.
        """
        from app.schemas.search import CandidateSource
        from app.services import source_classifier
        from app.services.source_discovery import discover_pages
        from app.schemas.source import SourceType

        # Build deduplicated query list from goals + fallback
        queries: list[str] = []
        seen_queries: set[str] = set()
        for goal in goals:
            for tpl in _GOAL_QUERY_TEMPLATES.get(goal, []):
                q = tpl.format(name=competitor_name)
                if q not in seen_queries:
                    seen_queries.add(q)
                    queries.append(q)
        if not queries:
            for tpl in _DEFAULT_SOURCE_QUERIES:
                q = tpl.format(name=competitor_name)
                if q not in seen_queries:
                    seen_queries.add(q)
                    queries.append(q)

        official_domains = _official_domains_for(competitor_name, website)

        seen_norms: set[str] = set()
        candidates: list[CandidateSource] = []
        cap = _SEARCH_MAX_URLS * 3
        core_source_types = {"official_website", "pricing_page", "docs", "features_page"}
        core_path_markers = (
            "/pricing", "/price", "/plans", "/docs", "/documentation", "/api", "/features"
        )

        def _process_hits(
            hits: list,
            seen: set[str],
            results: list[CandidateSource],
            *,
            official_pass: bool,
        ) -> bool:
            """Process hits into candidates. Returns True if cap reached."""
            for hit in hits:
                if not _is_crawlable(hit.url):
                    continue
                norm = _normalize_url(hit.url)
                if norm in seen:
                    continue
                seen.add(norm)

                s_type = source_classifier.classify(hit.url, hit.title, hit.snippet)
                type_str = s_type.value if isinstance(s_type, SourceType) else str(s_type)
                on_official = _is_official_url(hit.url, official_domains)
                hit_path = urlparse(hit.url).path.lower()
                looks_like_core_path = any(marker in hit_path for marker in core_path_markers)

                if official_pass and not on_official:
                    continue

                # Core evidence types must come from the competitor's own domains.
                # Third-party pricing/docs pages are supplementary at best and should
                # not crowd out official results or be treated as selectable core sources.
                if (
                    not official_pass
                    and not on_official
                    and (type_str in core_source_types or looks_like_core_path)
                ):
                    continue

                confidence = _infer_source_confidence(
                    type_str, hit.url, website, official_domains
                )
                reason = _infer_source_reason(type_str, hit.url)

                results.append(CandidateSource(
                    competitor_name=competitor_name,
                    url=hit.url,
                    title=hit.title,
                    snippet=hit.snippet,
                    suggested_source_type=s_type,
                    discovery_query=query,
                    provider="tavily",
                    confidence=confidence,
                    reason=reason,
                    selected_by_default=False,
                ))
                if len(results) >= cap:
                    return True
            return False

        # Pass 1: official domain priority search across all queries.
        for query in queries:
            if official_domains:
                try:
                    official_hits = self._provider.search(
                        query,
                        max_results=max_per_query,
                        search_depth="advanced",
                        include_domains=official_domains,
                    )
                    if _process_hits(
                        official_hits, seen_norms, candidates, official_pass=True
                    ):
                        break
                except Exception as exc:
                    logger.warning(
                        "SearchService.search_sources (official pass): query '%s' failed: %s",
                        query, exc,
                    )

            if len(candidates) >= cap:
                break

        # Pass 2: general web search only if no official-domain sources were found.
        if not candidates:
            for query in queries:
                try:
                    hits = self._provider.search(
                        query,
                        max_results=max_per_query,
                        search_depth="advanced",
                    )
                    if _process_hits(hits, seen_norms, candidates, official_pass=False):
                        break
                except Exception as exc:
                    logger.warning(
                        "SearchService.search_sources: query '%s' failed: %s", query, exc
                    )
                    continue

                if len(candidates) >= cap:
                    break

        # Pass 3: deterministic official URL fallback. Some official sites are
        # sparse or poorly indexed by search providers; the UI still needs
        # actionable official candidates instead of an empty panel.
        if not candidates and self._provider.__class__.__name__ != "NullSearchProvider":
            fallback_bases = [website]
            for domain in official_domains:
                base = f"https://{domain}"
                if _normalize_url(base) not in {_normalize_url(u) for u in fallback_bases}:
                    fallback_bases.append(base)

            for base_url in fallback_bases:
                for url in discover_pages(base_url, industry_type=industry_type):
                    if not _is_crawlable(url):
                        continue
                    norm = _normalize_url(url)
                    if norm in seen_norms:
                        continue
                    seen_norms.add(norm)

                    s_type = source_classifier.classify(url, "", "")
                    type_str = s_type.value if isinstance(s_type, SourceType) else str(s_type)
                    confidence = _infer_source_confidence(
                        type_str, url, website, official_domains
                    )
                    candidates.append(CandidateSource(
                        competitor_name=competitor_name,
                        url=url,
                        title=urlparse(url).netloc.removeprefix("www.") + urlparse(url).path,
                        snippet="Official URL pattern fallback; crawl before using as evidence.",
                        suggested_source_type=s_type,
                        discovery_query="official URL pattern fallback",
                        provider="heuristic",
                        confidence=confidence,
                        reason=_infer_source_reason(type_str, url),
                        selected_by_default=False,
                    ))
                    if len(candidates) >= cap:
                        break
                if len(candidates) >= cap:
                    break

        candidates.sort(key=lambda c: _SOURCE_TYPE_PRIORITY.get(c.suggested_source_type.value, 10))
        return candidates

    def discover_competitors(
        self,
        industry: str,
        industry_type: str = "general",
        max_results: int = _MAX_DISCOVERY_RESULTS,
    ) -> list:
        """Return CandidateCompetitor[] for user selection. Descriptions are display-only."""
        from app.schemas.discovery import CandidateCompetitor

        # M16.3: detect industry from the prompt and override the caller's
        # industry_type. The NL discovery panel does not send industry_type at
        # all, and the manual mode dropdown may be stale relative to the prompt.
        detected = _detect_industry_type(industry)
        product_target = _extract_product_discovery_target(industry)
        if not product_target and not detected:
            product_target = _extract_generic_product_target(industry)
        if product_target:
            _alias_key, display_name, product_industry_type = product_target
            detected = product_industry_type
        if detected and detected != industry_type:
            logger.info(
                "discover_competitors: overriding industry_type %r → %r from prompt %r",
                industry_type, detected, industry[:80],
            )
            industry_type = detected

        # When the industry is confidently detected, run static English query
        # templates so Chinese conversational fragments never leak into Tavily
        # queries (previously matched dict.youdao.com / Chinese SEO ads).
        if product_target:
            alias_key, display_name, _product_industry_type = product_target
            queries = _product_discovery_queries(display_name, alias_key)
        elif detected and industry_type in _STATIC_DISCOVERY_QUERIES:
            queries = list(_STATIC_DISCOVERY_QUERIES[industry_type])
            if industry_type == "social" and not re.search(
                r"\b(dating|date|singles?|friend|matchmaking|relationship)\b",
                industry,
                re.IGNORECASE,
            ):
                queries = [
                    q for q in queries
                    if "dating" not in q.lower() and "tinder" not in q.lower()
                ]
        else:
            templates = _DISCOVERY_TEMPLATES.get(industry_type, _DEFAULT_DISCOVERY_QUERIES)
            if industry_type == "social" and not re.search(
                r"\b(dating|date|singles?|friend|matchmaking|relationship)\b",
                industry,
                re.IGNORECASE,
            ):
                templates = [
                    t for t in templates
                    if "dating" not in t.lower() and "tinder" not in t.lower()
                ]
            queries = [t.format(industry=industry) for t in templates]

        seen_domains: set[str] = set()
        candidates: list[CandidateCompetitor] = []

        has_cjk_prompt = bool(re.search(r"[\u4e00-\u9fff]", industry))
        provider_available = self._provider.__class__.__name__ != "NullSearchProvider"
        seed_known_industries = {
            "ai_saas", "ai_search", "design_tools", "ecommerce",
            "local_services", "open_source",
        }
        if provider_available and product_target:
            alias_key, _display_name, _product_industry_type = product_target
            for product_name, product_website, product_domain, suggested_role, seed_reason in _PRODUCT_COMPETITOR_SEEDS.get(alias_key, ()):
                if product_domain in seen_domains:
                    continue
                seen_domains.add(product_domain)
                candidates.append(CandidateCompetitor(
                    name=product_name,
                    website=product_website,
                    description=seed_reason,
                    raw_title=product_name,
                    source_url=product_website,
                    domain=product_domain,
                    discovery_query=f"known {alias_key} competitors",
                    confidence="high",
                    relevance_score=96,
                    relevance_reason=f"known competitor/alternative for {alias_key}",
                    suggested_role=suggested_role,
                    role_confidence="high",
                    reason="Seeded from product competitor list; verify before adding.",
                ))
        elif provider_available and has_cjk_prompt and detected and industry_type in seed_known_industries:
            for product_name, product_website, product_domain in _KNOWN_PRODUCTS_BY_INDUSTRY.get(industry_type, ())[:6]:
                if product_domain in seen_domains:
                    continue
                seen_domains.add(product_domain)
                candidates.append(CandidateCompetitor(
                    name=product_name,
                    website=product_website,
                    description=f"Known benchmark product for {industry_type}.",
                    raw_title=product_name,
                    source_url=product_website,
                    domain=product_domain,
                    discovery_query=f"known {industry_type} benchmark",
                    confidence="high",
                    relevance_score=95,
                    relevance_reason=f"known {industry_type} benchmark product",
                    role_confidence="high",
                    reason="Seeded from industry benchmark list; verify before adding.",
                ))
        elif provider_available and has_cjk_prompt and detected == "social":
            social_benchmarks = (
                ("Instagram", "https://www.instagram.com", "instagram.com"),
                ("TikTok", "https://www.tiktok.com", "tiktok.com"),
                ("X", "https://x.com", "x.com"),
                ("Reddit", "https://www.reddit.com", "reddit.com"),
                ("Discord", "https://discord.com", "discord.com"),
            )
            for product_name, product_website, product_domain in social_benchmarks:
                seen_domains.add(product_domain)
                candidates.append(CandidateCompetitor(
                    name=product_name,
                    website=product_website,
                    description="Known social/community product; crawling may be limited by access controls.",
                    raw_title=product_name,
                    source_url=product_website,
                    domain=product_domain,
                    discovery_query="known social benchmark",
                    confidence="high",
                    relevance_score=95,
                    relevance_reason="known social/community benchmark product",
                    role_confidence="high",
                    reason="Seeded from industry benchmark list; verify before adding.",
                ))

        for query in queries:
            try:
                results = self._provider.search(
                    query, max_results=5, search_depth="advanced"
                )
            except Exception:
                logger.warning("discover_competitors: query %r failed", query)
                continue

            for r in results:
                norm = _normalize_url(r.url)
                if not _is_crawlable(norm):
                    continue
                domain = urlparse(norm).netloc.removeprefix("www.")

                for product_name, product_website, product_domain in _extract_known_products(
                    " ".join([r.title or "", r.snippet or ""]),
                    industry_type,
                ):
                    if product_domain in seen_domains:
                        continue
                    seen_domains.add(product_domain)
                    candidates.append(CandidateCompetitor(
                        name=product_name,
                        website=product_website,
                        description=(r.snippet or "")[:200],
                        raw_title=r.title or "",
                        source_url=r.url,
                        domain=product_domain,
                        discovery_query=query,
                        confidence="medium",
                        relevance_score=90,
                        relevance_reason=(
                            "known AI coding product mentioned in search result"
                            if industry_type == "ai_saas"
                            else f"known {industry_type} product mentioned in search result"
                        ),
                        role_confidence="high",
                        reason=f"Extracted from: {query}",
                    ))
                if any(domain == d or domain.endswith("." + d) for d in _DISCOVERY_BLOCKED_DOMAINS):
                    continue
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)

                raw_title = r.title or ""
                name = _extract_company_name(raw_title, r.url)
                website = f"https://{domain}"
                relevance_score, relevance_reason = _score_competitor_relevance(
                    name, raw_title, r.url, domain, query, industry_type
                )

                candidates.append(CandidateCompetitor(
                    name=name,
                    website=website,
                    description=(r.snippet or "")[:200],
                    raw_title=raw_title,
                    source_url=r.url,
                    domain=domain,
                    discovery_query=query,
                    confidence=(
                        "high" if relevance_score >= 70
                        else "medium" if relevance_score >= 40
                        else "low"
                    ),
                    relevance_score=relevance_score,
                    relevance_reason=relevance_reason,
                    role_confidence="medium",
                    reason=f"Found via: {query}",
                ))

            if len(candidates) >= max_results * 2:
                break

        candidates.sort(key=lambda c: c.relevance_score, reverse=True)
        candidates = [c for c in candidates if c.relevance_score >= _DISCOVERY_MIN_SCORE]
        return candidates[:max_results]
