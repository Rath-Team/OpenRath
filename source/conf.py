"""Sphinx configuration for OpenRath static documentation."""

from __future__ import annotations

import sys
import re
from pathlib import Path

from sphinx.search import SearchLanguage
from sphinx.search.en import english_stopwords

# Docstrings reference the installed package; allow local src/ without install.
_root = Path(__file__).resolve().parents[2]
_src = _root / "src"
if _src.is_dir():
    sys.path.insert(0, str(_src))

project = "OpenRath"
author = "OpenRath contributors"
copyright = "OpenRath contributors"

release = version = "1.0.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
html_static_path = ["_static"]
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "showcase",
    "user_guide",
    "tutorial/figures.md",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"
language = "zh_CN"
html_search_language = "openrath_zh"


class OpenRathMixedSearch(SearchLanguage):
    """Small mixed Chinese/Latin search tokenizer for the static docs.

    Sphinx 9.1's built-in Chinese search currently emits a JavaScript reference
    to ``ChineseStemmer`` while bundling the English stemmer implementation. This
    language keeps the Chinese UI locale and provides a deterministic search
    tokenizer that covers API identifiers and short Chinese terms without
    requiring jieba at build time.
    """

    lang = "openrath_zh"
    language_name = "OpenRathMixed"
    stopwords = english_stopwords
    _latin_re = re.compile(r"[A-Za-z0-9_]+")
    _cjk_re = re.compile(r"[\u3400-\u9fff]+")
    _synonyms = {
        "agent": ("智能体",),
        "backend": ("后端",),
        "install": ("安装",),
        "installation": ("安装",),
        "multiagent": ("multi", "agent", "多智能体"),
        "opensandbox": ("沙箱", "sandbox"),
        "sandbox": ("沙箱",),
        "session": ("会话", "上下文"),
        "tool": ("工具",),
        "workflow": ("工作流",),
        "上下文": ("session",),
        "后端": ("backend",),
        "多智能体": ("multiagent", "multi", "agent"),
        "安装": ("install", "installation"),
        "工作流": ("workflow",),
        "工具": ("tool",),
        "智能体": ("agent",),
        "沙箱": ("sandbox", "opensandbox"),
        "会话": ("session",),
    }
    js_splitter_code = r"""
var splitQuery = function(query) {
  const terms = [];
  const synonyms = {
    agent: ["智能体"],
    backend: ["后端"],
    install: ["安装"],
    installation: ["安装"],
    multiagent: ["multi", "agent", "多智能体"],
    opensandbox: ["沙箱", "sandbox"],
    sandbox: ["沙箱"],
    session: ["会话", "上下文"],
    tool: ["工具"],
    workflow: ["工作流"],
    "上下文": ["session"],
    "后端": ["backend"],
    "多智能体": ["multiagent", "multi", "agent"],
    "安装": ["install", "installation"],
    "工作流": ["workflow"],
    "工具": ["tool"],
    "智能体": ["agent"],
    "沙箱": ["sandbox", "opensandbox"],
    "会话": ["session"],
  };
  const latinRe = /[A-Za-z0-9_]+/g;
  const cjkRe = /[\u3400-\u9fff]+/g;
  let m;
  const addTerm = function(term) {
    const value = String(term).toLowerCase();
    if (value.length > 1) {
      terms.push(value);
    }
  };

  while ((m = latinRe.exec(query)) !== null) {
    addTerm(m[0]);
  }

  while ((m = cjkRe.exec(query)) !== null) {
    const s = m[0];
    if (s.length > 1) {
      addTerm(s);
    }
    for (let i = 0; i < s.length - 1; i += 1) {
      addTerm(s.slice(i, i + 2));
    }
  }

  const lower = query.toLowerCase();
  if (
    lower.includes("multi-agent") ||
    lower.includes("multi agent") ||
    lower.includes("multiagent")
  ) {
    addTerm("multiagent");
    addTerm("多智能体");
  }

  Array.from(terms).forEach(function(term) {
    (synonyms[term] || []).forEach(addTerm);
  });

  return Array.from(new Set(terms));
};
"""

    def split(self, input: str) -> list[str]:
        terms: list[str] = []
        terms.extend(m.group(0) for m in self._latin_re.finditer(input))
        for match in self._cjk_re.finditer(input):
            segment = match.group(0)
            if len(segment) > 1:
                terms.append(segment)
            terms.extend(segment[i : i + 2] for i in range(len(segment) - 1))

        lowered = input.lower()
        if (
            "multi-agent" in lowered
            or "multi agent" in lowered
            or "multiagent" in lowered
        ):
            terms.extend(("multiagent", "多智能体"))

        expanded: list[str] = []
        for term in terms:
            key = term.lower()
            expanded.append(key)
            expanded.extend(self._synonyms.get(key, ()))
        return list(dict.fromkeys(expanded))

    def stem(self, word: str) -> str:
        return word.lower()

    def word_filter(self, stemmed_word: str) -> bool:
        return len(stemmed_word) > 1

html_theme = "pydata_sphinx_theme"
html_title = f"{project} 文档"
html_css_files = ["openrath.css"]
html_theme_options = {
    "show_nav_level": 2,
    "navigation_depth": 4,
    "collapse_navigation": False,
    "pygments_light_style": "default",
    "pygments_dark_style": "native",
    "github_url": "https://github.com/Rath-Team/OpenRath",
    "use_edit_page_button": True,
}

html_context = {
    "default_mode": "auto",
    "github_user": "Rath-Team",
    "github_repo": "OpenRath",
    "github_version": "docs",
    "doc_path": "docs/source",
}

# 不生成通用索引 / 模块索引页（与首页去掉「索引与表格」一致）
html_use_index = False
html_domain_indices = False
autodoc_member_order = "bysource"
autodoc_typehints = "signature"

intersphinx_mapping = {
    "python": ("https://docs.python.org/zh-cn/3", None),
}

myst_enable_extensions = ["colon_fence", "deflist"]


def setup(app):
    app.add_search_language(OpenRathMixedSearch)
