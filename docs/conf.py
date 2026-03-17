"""Sphinx configuration for server API documentation."""

from __future__ import annotations

import os
import sys
from pathlib import Path


DOCS_DIR = Path(__file__).resolve().parent
SERVER_DIR = DOCS_DIR.parent
REPO_ROOT = SERVER_DIR.parent

# Allow imports like `app.*` during autodoc.
sys.path.insert(0, str(SERVER_DIR))
sys.path.insert(0, str(REPO_ROOT))

project = "TRAQ Server"
author = "Hammerdirt + OpenAI Codex"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

autosummary_generate = True
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "alabaster"
html_static_path = ["_static"]

