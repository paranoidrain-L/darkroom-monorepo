"""Tech Blog Monitor source catalog."""

from dataclasses import dataclass, field
from typing import Any

from products.tech_blog_monitor.defaults import DEFAULT_FEED_TIMEOUT


@dataclass
class FeedSource:
    name: str
    url: str
    category: str
    timeout: int = DEFAULT_FEED_TIMEOUT
    verify_ssl: bool = True
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    source_type: str = "rss"
    metadata: dict[str, Any] = field(default_factory=dict)


DEFAULT_FEEDS: list[FeedSource] = [
    FeedSource("OpenAI News", "https://openai.com/news/rss.xml", "行业风向标"),
    FeedSource("Google DeepMind", "https://deepmind.google/blog/rss.xml", "行业风向标"),
    FeedSource("NVIDIA Technical Blog", "https://developer.nvidia.com/blog/feed/", "行业风向标"),
    FeedSource("NVIDIA 官方博客", "https://blogs.nvidia.com/feed/", "行业风向标"),
    FeedSource("Meta Engineering", "https://engineering.fb.com/feed/", "行业风向标"),
    FeedSource("Google for Developers", "https://blog.google/technology/developers/rss/", "行业风向标"),
    FeedSource(
        "Microsoft Research Blog",
        "https://www.microsoft.com/en-us/research/blog/feed/",
        "行业风向标",
        enabled=False,
    ),
    FeedSource("a16z Future", "https://future.a16z.com/feed/", "行业风向标", enabled=False),
    FeedSource("CVF Open Access (cs.CV)", "https://arxiv.org/rss/cs.CV", "自动驾驶/3D感知"),
    FeedSource("Lilian Weng (Lil'Log)", "https://lilianweng.github.io/index.xml", "AI Agent/工程实践"),
    FeedSource("LangChain Blog", "https://blog.langchain.com/rss/", "AI Agent/工程实践", enabled=False),
    FeedSource("Sebastian Raschka", "http://magazine.sebastianraschka.com/feed", "AI Agent/工程实践"),
    FeedSource("Simon Willison", "https://simonwillison.net/atom/everything/", "AI Agent/工程实践"),
    FeedSource("Weaviate Blog", "https://www.weaviate.io/blog/rss.xml", "AI Agent/工程实践"),
    FeedSource("Lightning AI Blog", "https://lightning.ai/pages/blog/feed/", "AI Agent/工程实践"),
    FeedSource("GitHub Blog", "https://github.blog/feed/", "AI Agent/工程实践"),
    FeedSource(
        "The Batch (Andrew Ng)",
        "https://charonhub.deeplearning.ai/rss/",
        "深度技术",
    ),
    FeedSource("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "深度技术"),
    FeedSource("Andrej Karpathy", "https://karpathy.github.io/feed.xml", "深度技术"),
    FeedSource("PyTorch Blog", "https://pytorch.org/blog/feed/", "深度技术"),
    FeedSource("AWS Machine Learning Blog", "https://aws.amazon.com/blogs/machine-learning/feed/", "深度技术"),
    FeedSource("BAIR Blog", "https://bair.berkeley.edu/blog/feed.xml", "深度技术"),
    FeedSource("Netflix Tech Blog", "https://netflixtechblog.com/feed", "深度技术", verify_ssl=False),
    FeedSource("Cloudflare Blog", "https://blog.cloudflare.com/rss/", "深度技术"),
    FeedSource("Spotify Engineering", "https://engineering.atspotify.com/feed/", "深度技术"),
    FeedSource("Trail of Bits Blog", "https://blog.trailofbits.com/feed/", "深度技术"),
    FeedSource("The Pragmatic Engineer", "https://blog.pragmaticengineer.com/rss/", "深度技术"),
    FeedSource(
        "Uber Engineering",
        "https://www.uber.com/en-US/blog/engineering/rss/",
        "深度技术",
        enabled=False,
    ),
    FeedSource(
        "uv Releases",
        "https://api.github.com/repos/astral-sh/uv/releases",
        "AI Agent/工程实践",
        source_type="github_releases",
    ),
    FeedSource(
        "OpenAI Agents Python Releases",
        "https://api.github.com/repos/openai/openai-agents-python/releases",
        "AI Agent/工程实践",
        source_type="github_releases",
    ),
    FeedSource(
        "browser-use Releases",
        "https://api.github.com/repos/browser-use/browser-use/releases",
        "AI Agent/工程实践",
        source_type="github_releases",
    ),
    FeedSource(
        "Gemini CLI Releases",
        "https://api.github.com/repos/google-gemini/gemini-cli/releases",
        "AI Agent/工程实践",
        source_type="github_releases",
    ),
    FeedSource(
        "Goose Releases",
        "https://api.github.com/repos/aaif-goose/goose/releases",
        "AI Agent/工程实践",
        source_type="github_releases",
    ),
    FeedSource(
        "Pydantic Releases",
        "https://api.github.com/repos/pydantic/pydantic/releases",
        "AI Agent/工程实践",
        enabled=False,
        source_type="github_releases",
    ),
    FeedSource(
        "FastAPI Release History",
        "https://pypi.org/pypi/fastapi/json",
        "AI Agent/工程实践",
        source_type="changelog",
        metadata={"format": "pypi"},
    ),
]
