"""Sync copier.yml's dough version pin to dough.__version__."""

import re
from pathlib import Path

from dough.__about__ import __version__

major, minor = __version__.split(".")[:2]
pin = f">={major}.{minor},<{major}.{int(minor) + 1}"

cfg = Path("copier.yml")
cfg.write_text(re.sub(r"'dough\[pint\][^']*'", f"'dough[pint]{pin}'", cfg.read_text()))
