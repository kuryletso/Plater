"""UI preferences: an ini file beside the database, deliberately separate from
the template defaults that live in the database and describe documents."""

import pytest


@pytest.fixture(autouse=True)
def settings_file(tmp_path, monkeypatch):
    """Redirect the store, or these tests would rewrite the developer's own
    preferences."""

    path = tmp_path / "plater.ini"
    monkeypatch.setenv("PLATER_SETTINGS", str(path))
    return path


@pytest.fixture
def store(qt_app):
    """QSettings needs no application object, but the GUI modules import Qt."""
    from app.gui import settings

    return settings


# --- reading -----------------------------------------------------------------

def test_a_fresh_install_falls_back_to_english(store):
    assert store.ui_language() == "ENG"


def test_the_language_round_trips(store, settings_file):
    store.set_ui_language("UKR")

    assert settings_file.exists()
    assert store.ui_language() == "UKR"


def test_the_value_survives_a_new_reader(store):
    """Each call opens its own QSettings; the file is the state, not the object."""
    store.set_ui_language("UKR")

    assert store.ui_language() == "UKR"


def test_a_hand_edited_file_cannot_break_the_app(store, settings_file):
    """The file is user-editable, so an unknown code falls back rather than
    propagating into every localized() call."""
    settings_file.write_text("[ui]\nlanguage=KLINGON\n", encoding="utf-8")

    assert store.ui_language() == "ENG"


def test_an_empty_file_falls_back(store, settings_file):
    settings_file.write_text("", encoding="utf-8")

    assert store.ui_language() == "ENG"


def test_writing_an_unsupported_language_is_refused(store):
    with pytest.raises(ValueError):
        store.set_ui_language("FRA")


# --- display order -----------------------------------------------------------

def test_display_languages_puts_the_choice_first(store):
    assert store.display_languages("UKR") == ("UKR", "ENG")
    assert store.display_languages("ENG") == ("ENG", "UKR")


def test_display_languages_keeps_the_other_as_a_fallback(store):
    """Reference data is often translated in only one language; a real name
    beats a '?'."""
    assert set(store.display_languages("UKR")) == {"ENG", "UKR"}


def test_display_languages_follows_the_stored_setting(store):
    store.set_ui_language("UKR")

    assert store.display_languages() == ("UKR", "ENG")


# --- what the setting actually changes ---------------------------------------

def test_localized_follows_the_preferred_order(qt_app, session, make_org):
    from app.gui.text import localized, set_preferred_languages

    organization = make_org("Acme")          # ENG "Acme", UKR "Acme UA"

    set_preferred_languages(("ENG", "UKR"))
    assert localized(organization.localizations, "legal_name") == "Acme"

    set_preferred_languages(("UKR", "ENG"))
    assert localized(organization.localizations, "legal_name") == "Acme UA"

    set_preferred_languages(("ENG", "UKR"))  # leave the module as we found it


def test_localized_falls_back_when_the_choice_is_missing(qt_app, session, make_org):
    from app.gui.text import localized, set_preferred_languages

    organization = make_org("Acme")
    del organization.localizations["UKR"]

    set_preferred_languages(("UKR", "ENG"))
    try:
        assert localized(organization.localizations, "legal_name") == "Acme"
    finally:
        set_preferred_languages(("ENG", "UKR"))


def test_the_display_language_does_not_limit_what_can_be_typed(qt_app, session):
    """The alias work means switching language changes only what is shown."""
    from app.gui.dialogs.widgets import country_items, searchable_combo
    from app.gui.text import set_preferred_languages

    set_preferred_languages(("UKR", "ENG"))
    try:
        combo = searchable_combo(country_items(session))
        for typed in ("Ukraine", "Україна", "UKR"):
            combo.lineEdit().setText(typed)
            assert combo.code() == "UKR", typed
    finally:
        set_preferred_languages(("ENG", "UKR"))
