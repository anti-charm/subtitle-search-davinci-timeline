"""Sort table rows without changing their identities or backing search order."""

from __future__ import annotations

import re
from tkinter import ttk

_PAIRING_ORDER = {"unresolved": 0, "ambiguous": 1, "normalized": 2, "exact": 3, "manual": 4}


class TableSorter:
    def __init__(self, tree: ttk.Treeview):
        self.tree = tree
        self.column: str | None = None
        self.descending = False
        self.titles = {column: tree.heading(column, "text") for column in tree["columns"]}
        for column in self.titles:
            tree.heading(column, command=lambda column=column: self.sort(column))

    def sort(self, column: str) -> None:
        self.descending = not self.descending if column == self.column else False
        self.column = column
        self.apply()
        self.tree.yview_moveto(0)

    def _key(self, row: str):
        value = self.tree.set(row, self.column)
        if self.column in {"status", "pairing"}:
            return _PAIRING_ORDER.get(value, 5)
        if self.column in {"start", "end"}:
            # Numeric hours also sort correctly for durations above 99 hours.
            return tuple(int(part) for part in re.split(r"[:.]", value))
        if self.column == "use":
            return value not in {"☑", "✓"}
        if self.column == "video":
            return value != "—", value.casefold()
        return value.casefold()

    def apply(self) -> None:
        if self.column is not None:
            rows = sorted(self.tree.get_children(), key=self._key, reverse=self.descending)
            for position, row in enumerate(rows):
                self.tree.move(row, "", position)
        for column, title in self.titles.items():
            arrow = (" ▼" if self.descending else " ▲") if column == self.column else ""
            self.tree.heading(column, text=title + arrow)

    def restore(self, selection: tuple[str, ...], focus: str, scroll: float) -> None:
        """Restore surviving selections after a table rebuild, then reapply its sort."""
        self.apply()
        self.tree.selection_set([row for row in selection if self.tree.exists(row)])
        if self.tree.exists(focus):
            self.tree.focus(focus)
        self.tree.yview_moveto(scroll)
