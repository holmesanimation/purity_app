# purity_app/gui/log_normalizer_sink.py
"""PurityLogNormalizerSink — converts journal envelopes into LogRows for the purity log viewer."""
from __future__ import annotations

from shane_common.ui.log_viewer.base_normalizer_sink import BaseLogNormalizerSink
from shane_common.ui.log_viewer.log_row_emitter import LogRowEmitter, LogRowEmitterProtocol

try:
    from purity_app.services.log_kind_map import (
        PURITY_TYPE_LABELS,
        classify_purity_row_type,
        spec_for_purity_kind,
    )
except ModuleNotFoundError:
    from services.log_kind_map import (  # type: ignore[no-redef]
        PURITY_TYPE_LABELS,
        classify_purity_row_type,
        spec_for_purity_kind,
    )


class PurityLogNormalizerSink(BaseLogNormalizerSink):
    """Sink that normalises purity_app envelopes into ``LogRow`` objects.

    Plug into ``runtime.journal._sinks`` at startup. Connect ``emitter.log_row_appended``
    to ``PurityLogViewerWindow`` in ``app.py``.
    """

    def __init__(self) -> None:
        super().__init__(kind_spec_fn=spec_for_purity_kind, emitter=LogRowEmitter())

    @property
    def emitter(self) -> LogRowEmitterProtocol:
        return self._emitter

    @property
    def type_classifier(self):
        return classify_purity_row_type

    @property
    def type_labels(self):
        return dict(PURITY_TYPE_LABELS)
