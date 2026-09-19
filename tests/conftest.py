from __future__ import annotations

from collections.abc import Iterator

import pytest

from eew.official import clear_source_pauses


@pytest.fixture(autouse=True)
def _no_official_source_pauses() -> Iterator[None]:
    """Las pausas por rechazo viven en el proceso; una prueba no hereda la de otra."""

    clear_source_pauses()
    yield
    clear_source_pauses()
