from __future__ import annotations

from antenati.gui.progress import TkProgress


class _Master:
    def after(self, _delay: int, callback, *args) -> None:
        callback(*args)


class _ProgressBar:
    def __init__(self) -> None:
        self.master = _Master()
        self.values: dict[str, object] = {'mode': 'determinate', 'value': 0}
        self.started: list[int] = []
        self.stop_calls = 0

    def configure(self, **kwargs) -> None:
        self.values.update(kwargs)

    def start(self, interval: int) -> None:
        self.started.append(interval)

    def stop(self) -> None:
        self.stop_calls += 1

    def __setitem__(self, key: str, value: object) -> None:
        self.values[key] = value


def test_indeterminate_loading_switches_to_determinate_download() -> None:
    widget = _ProgressBar()
    progress = TkProgress(widget)  # type: ignore[arg-type]

    progress.start_indeterminate()
    assert widget.values['mode'] == 'indeterminate'
    assert widget.started

    progress.set_total(15)
    assert widget.values['mode'] == 'determinate'
    assert widget.values['maximum'] == 15
    assert widget.values['value'] == 0

    progress.update()
    progress.update()
    assert widget.values['value'] == 2
    assert progress.current == 2
    assert progress.total == 15


def test_reset_stops_animation_and_clears_progress() -> None:
    widget = _ProgressBar()
    progress = TkProgress(widget)  # type: ignore[arg-type]

    progress.start_indeterminate()
    progress.reset()

    assert widget.values['mode'] == 'determinate'
    assert widget.values['value'] == 0
    assert progress.current == 0
    assert progress.total == 0
