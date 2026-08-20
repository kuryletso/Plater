from __future__ import annotations

from typing import Any

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal, QPersistentModelIndex
from PySide6.QtGui import QBrush, QColor

from app.gui.draft_state import LineRow

WARNING_TINT = QColor(255, 244, 214)


@dataclass(slots=True, frozen=True)
class GridColumn:
    kind: str       # description | unit | quantity | price | tax
    header: str
    language: str | None = None


class LinesModel(QAbstractTableModel):
    """Rows are LineRow. The description columns follow the template's rendered languages,
    so the grid reshapes when the template changes.
    """

    rows_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[LineRow] = [LineRow()]
        self._columns: list[GridColumn] = []
        self._unit_names: dict[str, str] = {}
        self._primary: str | None = None


    def set_languages(self, languages: tuple[str, ...]) -> None:
        self.beginResetModel()
        self._primary = languages[0] if languages else None
        named = len(languages) > 1

        self._columns = [
            GridColumn(
                "description",
                f"Description ({code})" if named else "Description",
                code,
            )
            for code in languages
        ] + [
            GridColumn("unit", "Unit"),
            GridColumn("quantity", "Qty"),
            GridColumn("price", "Price"),
            GridColumn("tax", "Tax %"),
        ]
        self.endResetModel()


    def set_unit_names(self, names: dict[str, str]) -> None:
        self._unit_names = names

    def column_kinds(self) -> list[str]:
        return [ column.kind for column in self._columns ]

    def rows(self) -> tuple[LineRow, ...]:
        return tuple(self._rows)


    # --- Qt model interface ---

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def headerData(
            self,
            section: int,
            orientation: Qt.Orientation,
            role: int =Qt.ItemDataRole.DisplayRole,
        ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section].header
        return section + 1


    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )


    def data(
            self,
            index: QModelIndex | QPersistentModelIndex,
            role: int = Qt.ItemDataRole.DisplayRole,
        ) -> Any:
        if not index.isValid():
            return None

        row = self._rows[index.row()]
        column = self._columns[index.column()]

        if role == Qt.ItemDataRole.EditRole:
            return self._raw(row, column)

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(row, column)

        if self._prints_blank(row, column):
            if role == Qt.ItemDataRole.BackgroundRole:
                return QBrush(WARNING_TINT)
            if role == Qt.ItemDataRole.ToolTipRole:
                return (
                    f"This template renders {column.language} descriptions; "
                    f"this line will print blank."
                )

        return None


    def setData(
            self,
            index: QModelIndex | QPersistentModelIndex,
            value: Any,
            role: int = Qt.ItemDataRole.EditRole,
        ) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False

        row = self._rows[index.row()]
        column = self._columns[index.column()]

        match column.kind:
            case "description":
                row.descriptions[column.language or ""] = str(value or "")
            case "unit":
                row.unit_code = value or None
            case "quantity":
                row.quantity = value
            case "price":
                row.unit_price = value
            case "tax":
                row.tax_rate = value

        self.dataChanged.emit(index, index)
        self.rows_changed.emit()
        return True

    # --------------------------


    def add_row(self) -> None:
        position = len(self._rows)
        self.beginInsertRows(QModelIndex(), position, position)
        self._rows.append(LineRow())
        self.endInsertRows()
        self.rows_changed.emit()


    def remove_row(self, position: int) -> None:
        if not 0 <= position < len(self._rows):
            return

        self.beginRemoveRows(QModelIndex(), position, position)
        del self._rows[position]

        self.endRemoveRows()

        if not self._rows:
            self.add_row()
        else:
            self.rows_changed.emit()


    def move_row(self, position: int, delta: int) -> bool:
        target = position + delta
        if not (0 <= position < len(self._rows) and 0 <= target < len(self._rows)):
            return False

        destination = target + 1 if delta > 0 else target
        self.beginMoveRows(QModelIndex(), position, position, QModelIndex(), destination)
        self._rows.insert(target, self._rows.pop(position))
        self.endMoveRows()
        self.rows_changed.emit()
        return True


    def fill_row(self, position: int, line) -> None:
        """A chosen hint fills the row except quantity, which is per-invoice."""

        if not 0 <= position < len(self._rows):
            return

        row = self._rows[position]
        row.descriptions = {
            code: localization.description
            for code, localization in line.localizations.items()
        }
        row.unit_code = line.measurement_unit_code
        row.unit_price = line.unit_price
        row.tax_rate = line.tax_rate

        self.dataChanged.emit(
            self.index(position, 0),
            self.index(position, len(self._columns) - 1),
        )
        self.rows_changed.emit()


    def _raw(self, row: LineRow, column: GridColumn) -> Any:
        match column.kind:
            case "description":
                return row.descriptions.get(column.language or "", "")
            case "unit":
                return row.unit_code
            case "quantity":
                return row.quantity
            case "price":
                return row.unit_price
            case "tax":
                return row.tax_rate


    def _display(self, row: LineRow, column: GridColumn) -> str:

        match column.kind:
            case "description":
                return row.descriptions.get(column.language or "", "")
            case "unit":
                code = row.unit_code
                if code is None:
                    return ""
                return self._unit_names.get(code, code)     # localized name, else the code
            case "quantity":
                return "" if row.quantity is None else format(row.quantity.normalize(), "f")
            case "price":
                return "" if row.unit_price is None else f"{row.unit_price:.2f}"
            case _:
                return (
                    "" if row.tax_rate is None
                    else f"{format((row.tax_rate * 100).normalize(), "f")}%"
                )


    def _prints_blank(self, row: LineRow, column: GridColumn) -> bool:
        """Rendered-but-empty secondary description warns, doesn't block."""

        return (
            column.kind == "description"
            and column.language != self._primary
            and not row.is_blank()
            and not row.descriptions.get(column.language or "", "").strip()
        )