from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QListWidgetItem, QWidget
from sqlalchemy.orm import Session

from app.gui.draft_state import DraftState
from app.gui.generated.ui_party_column import Ui_PartyColumn
from app.services.doc_sequence.repository import SequenceRepository
from app.services.organization.repository import OrganizationRepository


PREFERRED_LANGUAGES = ("ENG", "UKR")


def localized(localizations, attr: str) -> str:
    for code in PREFERRED_LANGUAGES:
        row = localizations.get(code)
        if row is not None and getattr(row, attr):
            return getattr(row, attr)
    for row in localizations.values():
        if getattr(row, attr):
            return getattr(row, attr)
    return "?"


class PartyRole(StrEnum):
    PROVIDER = "provider"
    CLIENT = "client"


class PartyColumn(QWidget):
    """Pick an organization and its details. The provider also picks
    the numbering sequence, filtered by organization + template document type.
    """

    def __init__(
            self,
            session: Session,
            draft: DraftState,
            role: PartyRole,
            parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)
        self._org_repo = OrganizationRepository(session)
        self._seq_repo = SequenceRepository(session)
        self._draft = draft
        self._role = role
        self._sequence_key: tuple | None = None

        if role is PartyRole.PROVIDER:
            self._set_org = draft.set_provider_organization
            self._set_tax = draft.set_provider_tax
            self._set_representative = draft.set_provider_representative
            self._set_bank = draft.set_provider_bank
            self._get_org = lambda: draft.provider_organization_id
        else:
            self._set_org = draft.set_client_organization
            self._set_tax = draft.set_client_tax
            self._set_representative = draft.set_client_representative
            self._set_bank = draft.set_client_bank
            self._get_org = lambda: draft.client_organization_id

        self.ui = Ui_PartyColumn()
        self.ui.setupUi(self)

        if role is PartyRole.CLIENT:
            self.ui.sequence_label.hide()
            self.ui.sequence_combo.hide()

        self.ui.clear_button.clicked.connect(self.clear_selection)
        self._show_selected(None)

        self.ui.tax_combo.setPlaceholderText("Select...")
        self.ui.sequence_combo.setPlaceholderText("Select a template first...")
        self.ui.sequence_combo.setEnabled(False)

        self.ui.search_edit.textChanged.connect(self.refresh_organizations)
        self.ui.organization_list.currentItemChanged.connect(self._on_org_selected)
        self.ui.tax_combo.currentIndexChanged.connect(self._on_tax_changed)

        self.ui.representative_combo.currentIndexChanged.connect(self._on_representative_changed)
        self.ui.bank_combo.currentIndexChanged.connect(self._on_bank_changed)
        self.ui.sequence_combo.currentIndexChanged.connect(self._on_sequence_changed)

        draft.changed.connect(self._on_draft_changed)

        self.refresh_organizations()


    def refresh_organizations(self) -> None:
        """Filtering is a view change: the selection lives in DraftState and survives it."""

        search = self.ui.search_edit.text().strip() or None
        selected = self._get_org()

        widget = self.ui.organization_list
        with QSignalBlocker(widget):
            widget.clear()
            organizations = self._org_repo.list(search=search)
            for org in organizations:
                item = QListWidgetItem(localized(org.localizations, "legal_name"))
                item.setData(Qt.ItemDataRole.UserRole, org.id)
                widget.addItem(item)

                if org.id == selected:
                    widget.setCurrentItem(item)
            if not organizations:
                self._show_empty_notice(search)


    def clear_selection(self) -> None:
        with QSignalBlocker(self.ui.organization_list):
            self.ui.organization_list.setCurrentRow(-1)

        self._set_org(None)
        self._clear_pickers()
        self._show_selected(None)


    def _on_org_selected(
            self,
            current: QListWidgetItem | None,
            _previous: QListWidgetItem | None = None,
    ) -> None:

        if current is None:
            self._set_org(None)
            self._clear_pickers()
            return

        organization_id = current.data(Qt.ItemDataRole.UserRole)
        self._set_org(organization_id)
        self._populate_pickers(organization_id)


    def _clear_pickers(self) -> None:
        for combo in (
            self.ui.tax_combo,
            self.ui.representative_combo,
            self.ui.bank_combo,
        ):
            with QSignalBlocker(combo):
                combo.clear()

        self._populate_sequences()


    def _populate_pickers(self, organization_id: int) -> None:
        org = self._org_repo.get(organization_id)
        self._show_selected(localized(org.localizations, "legal_name"))

        with QSignalBlocker(self.ui.tax_combo):
            self.ui.tax_combo.clear()
            for tax in org.tax_ids:
                self.ui.tax_combo.addItem(
                    f"{tax.value} ({tax.tax_id_system_code})",
                    tax.id,
                )
            self.ui.tax_combo.setCurrentIndex(-1)

        with QSignalBlocker(self.ui.representative_combo):
            self.ui.representative_combo.clear()
            self.ui.representative_combo.addItem("--", None)
            for rep in org.representatives:
                self.ui.representative_combo.addItem(
                    localized(rep.localizations, "name"), rep.id,
                )

        with QSignalBlocker(self.ui.bank_combo):
            self.ui.bank_combo.clear()
            self.ui.bank_combo.addItem("--", None)
            for bank in org.bank_accounts:
                self.ui.bank_combo.addItem(
                    f"{localized(bank.localizations, "bank_name")} | {bank.iban}",
                    bank.id,
                )

        if self.ui.tax_combo.count() == 1:
            self.ui.tax_combo.setCurrentIndex(0)

        self._populate_sequences()


    def _populate_sequences(self) -> None:
        if self._role is not PartyRole.PROVIDER:
            return

        organization_id = self._draft.provider_organization_id
        document_type = self._draft.document_type
        self._sequence_key = (organization_id, document_type)

        combo = self.ui.sequence_combo
        with QSignalBlocker(combo):
            combo.clear()

        if organization_id is None or document_type is None:
            combo.setPlaceholderText(
                "Select a template first" if document_type is None
                else "Select an organization first"
            )
            combo.setEnabled(False)
            return

        sequences = self._seq_repo.list(
            organization_id=organization_id,
            document_type=document_type,
        )

        with QSignalBlocker(combo):
            for sequence in sequences:
                preview = f"{sequence.prefix or ''}" \
                          f"{str(sequence.counter + 1).zfill(sequence.padding)}"
                combo.addItem(
                    f"{sequence.prefix or '(no prefix)'} — next {preview}",
                    sequence.id,
                )

            combo.setCurrentIndex(-1)

        combo.setEnabled(bool(sequences))
        combo.setPlaceholderText(
            "Select..." if sequences
            else "No sequences for this organization"
        )

        if combo.count() == 1:
            combo.setCurrentIndex(0)


    def _on_tax_changed(self, index: int) -> None:
        self._set_tax(self.ui.tax_combo.itemData(index) if index >= 0 else None)

    def _on_representative_changed(self, index: int) -> None:
        self._set_representative(self.ui.representative_combo.itemData(index) if index >= 0 else None)

    def _on_bank_changed(self, index: int) -> None:
        self._set_bank(self.ui.bank_combo.itemData(index) if index >= 0 else None)

    def _on_sequence_changed(self, index: int) -> None:
        self._draft.set_sequence(
            self.ui.sequence_combo.itemData(index) if index >= 0 else None
        )


    def _on_draft_changed(self) -> None:
        """Only the sequence picker depends on state set outside this column."""

        if self._role is not PartyRole.PROVIDER:
            return

        key = (
            self._draft.provider_organization_id,
            self._draft.document_type,
        )
        if key != self._sequence_key:
            self._populate_sequences()


    def _show_selected(self, name: str | None) -> None:
        """The list may be filtered away from the selection, so name it here."""

        self.ui.selection_label.setText(name or "Nothing selected")
        self.ui.selection_label.setEnabled(name is not None)
        self.ui.clear_button.setEnabled(name is not None)


    def _show_empty_notice(self, search: str | None) -> None:
        item = QListWidgetItem(
            f'No matches for "{search}"' if search else "No organization yet"
        )

        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ui.organization_list.addItem(item)