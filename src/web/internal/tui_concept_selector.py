# file: src/web/internal/tui_concept_selector.py

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Timer

from prompt_toolkit import prompt
from prompt_toolkit.completion import Completer, Completion

from pod.paths import concepts_root


class DebouncedConceptCache:
    """Cache autocomplete results for concept names with a small debounce delay."""
    def __init__(self, target_folder: Path, delay: float = 0.25):
        self.target_folder = target_folder
        self.delay = delay

        self._timer = None
        self._last_query = ""
        self._last_result = []

    def _request(self, prefix: str) -> list[str]:
        prefix = prefix.lower()

        if prefix == self._last_query:
            return self._last_result

        self._last_query = prefix

        if self._timer:
            self._timer.cancel()

        self._timer = Timer(
            self.delay,
            self._compute,
            args=(prefix,)
        )
        self._timer.start()

        return self._last_result

    def _compute(self, prefix: str):
        """Refresh the cached list of matching concept names for the given prefix."""
        try:
            root = concepts_root(self.target_folder)
        except FileNotFoundError:
            self._last_result = []
            return

        results = [
            name
            for name in os.listdir(root)
            if name.lower().startswith(prefix)
        ]

        self._last_result = sorted(results)[:10]


class ConceptCompleter(Completer):
    """Prompt-toolkit completer that suggests concept names from the target folder."""

    def __init__(self, target_folder: Path):
        self.cache = DebouncedConceptCache(target_folder)

    def get_completions(self, document, complete_event):
        text = document.text.strip()

        for name in self.cache._request(text):
            yield Completion(
                name,
                start_position=-len(text)
            )




def _run_selection_prompt(target_folder: Path) -> str:
    """Run the interactive concept prompt in the current terminal context."""
    return prompt(
        "Concept: ",
        completer=ConceptCompleter(target_folder),
        complete_while_typing=True
    )


def select_concept(target_folder: Path) -> str:
    """Prompt the user to choose a concept by name using autocomplete in its own console window."""
    if os.environ.get("POD_TUI_CHILD") == "1":
        return _run_selection_prompt(target_folder)

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".tmp") as handle:
        result_path = Path(handle.name)

    env = os.environ.copy()
    env["POD_TUI_CHILD"] = "1"
    env["POD_TUI_RESULT_PATH"] = str(result_path)

    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), str(target_folder)],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        env=env,
    ).wait()

    try:
        if result_path.exists():
            return result_path.read_text(encoding="utf-8").strip()
        return ""
    finally:
        if result_path.exists():
            result_path.unlink(missing_ok=True)


if __name__ == "__main__":
    target_folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    result_path = Path(os.environ.get("POD_TUI_RESULT_PATH", ""))

    if result_path:
        result_path.write_text(_run_selection_prompt(target_folder), encoding="utf-8")
    else:
        print(_run_selection_prompt(target_folder))