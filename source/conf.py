"""Sphinx configuration for OpenRath static documentation."""

from __future__ import annotations

import sys
from pathlib import Path

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
language = "en"
html_search_language = "en"

html_theme = "pydata_sphinx_theme"
html_title = f"{project} Documentation"
html_css_files = ["openrath.css"]
html_js_files = ["openrath-search.js"]
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

# Do not generate general or module index pages.
html_use_index = False
html_domain_indices = False
autodoc_member_order = "bysource"
autodoc_typehints = "signature"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

myst_enable_extensions = ["colon_fence", "deflist"]
