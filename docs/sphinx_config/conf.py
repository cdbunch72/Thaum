# Sphinx configuration for Thaum documentation.
# Build from repo root:
#   sphinx-build -c docs/sphinx_config docs docs/_build/html
# Or use the Makefile in this directory: make -C docs/sphinx_config html

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

_conf_dir = os.path.dirname(os.path.abspath(__file__))
_doc_root = os.path.abspath(os.path.join(_conf_dir, ".."))
_repo_root = os.path.abspath(os.path.join(_doc_root, ".."))

sys.path.insert(0, _repo_root)
sys.path.insert(0, os.path.join(_repo_root, "scripts", "python"))

# -- Project metadata ---------------------------------------------------------

project = "Thaum"
author = "Gemstone Software"
copyright = f"{datetime.now().year}, {author}"

_release = "0.0.0"
_pyproject = os.path.join(_repo_root, "pyproject.toml")
if os.path.isfile(_pyproject):
    with open(_pyproject, "rb") as f:
        _release = tomllib.load(f)["project"]["version"]
release = _release
version = release

# -- General ------------------------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_design",
    "sphinx_copybutton",
]

root_doc = "index"
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
language = "en"

templates_path = []
exclude_patterns = [
    "_build",
    "sphinx_config/_build",
    "Thumbs.db",
    ".DS_Store",
]

suppress_warnings = [
    "myst.xref_missing",
    "autodoc.duplicate_object",
]

pygments_style = "sphinx"
highlight_language = "bash"

# MyST: allow Markdown docs alongside RST API pages.
myst_heading_anchors = 3
myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

# Napoleon: Google-style docstrings on plugin base classes and scripts.
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_use_param = True
napoleon_use_rtype = True

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autodoc_mock_imports = [
    "gemstone_utils",
    "webexpythonsdk",
    "ldap3",
    "flask",
    "sqlalchemy",
    "psycopg",
]

# sphinx-design: tab-set / tab-item
sphinx_design_tabs_dynamic = False

# -- HTML (Furo) --------------------------------------------------------------

html_theme = "furo"
html_title = project
html_short_title = "Thaum"
html_static_path = ["_static"]

html_theme_options = {
    "light_logo": "Thaum_wizard_cgi.jpg",
    "dark_logo": "Thaum_wizard_cgi.jpg",
    "light_css_variables": {
        "font-stack": '"Open Sans", ui-sans-serif, system-ui, sans-serif',
        "font-stack--monospace": '"Source Code Pro", ui-monospace, monospace',
        "color-thaum-heading-border": "#2e7d4a",
        "color-sidebar-background": "#eaf5ef",
        "color-table-header-background": "var(--color-sidebar-background)",
        "color-code-background": "#eef0f3",
        "color-thaum-target-accent": "#6D28D9",
    },
    "dark_css_variables": {
        "font-stack": '"Open Sans", ui-sans-serif, system-ui, sans-serif',
        "font-stack--monospace": '"Source Code Pro", ui-monospace, monospace',
        "color-thaum-heading-border": "#5cb87a",
        "color-sidebar-background": "#0d1a12",
        "color-table-header-background": "#15241b",
        "color-thaum-target-accent": "#C4B5FD",
    },
}

# -- Plain text ---------------------------------------------------------------

text_newlines = "unix"


# -- Extension setup ----------------------------------------------------------

_LOGO_SIZE = 128
_LOGO_NAME = "Thaum_wizard_cgi.jpg"
_LOGO_SRC = os.path.join(_repo_root, "static", _LOGO_NAME)
_LOGO_DST = os.path.join(_conf_dir, "_static", _LOGO_NAME)


def _resize_logo(src: str, dst: str, size: int) -> None:
    """Write a square logo JPEG; use Pillow when available."""
    try:
        from PIL import Image
    except ImportError:
        import shutil

        shutil.copy2(src, dst)
        return

    with Image.open(src) as img:
        img.convert("RGB").resize((size, size), Image.Resampling.LANCZOS).save(
            dst, format="JPEG", quality=90
        )


def _ensure_logo_asset() -> None:
    if not os.path.isfile(_LOGO_SRC):
        return
    os.makedirs(os.path.dirname(_LOGO_DST), exist_ok=True)
    _resize_logo(_LOGO_SRC, _LOGO_DST, _LOGO_SIZE)


def _neutralize_markdown_rules(app, docname, source) -> None:
    """Replace Markdown thematic-break lines so docutils does not emit transitions."""
    try:
        if Path(app.env.doc2path(docname)).suffix != ".md":
            return
    except Exception:
        return
    for i, line in enumerate(source):
        stripped = line.strip()
        if len(stripped) >= 4 and set(stripped) <= {"-"}:
            source[i] = "\n"


def _on_builder_inited(app) -> None:
    if app.builder.format != "html":
        return
    _ensure_logo_asset()
    app.add_css_file("custom.css")


def setup(app):
    _ensure_logo_asset()
    app.connect("source-read", _neutralize_markdown_rules)
    app.connect("builder-inited", _on_builder_inited)
    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
