from app.db.models.references.country import Country
from app.db.models.references.country_localization import CountryLocalization
from app.db.models.references.currency import Currency
from app.db.models.references.currency_localization import CurrencyLocalization
from app.db.models.references.language import Language
from app.db.models.registries.document_type import DocumentTypeRegistry
from app.db.models.registries.document_type_localization import (
    DocumentTypeRegistryLocalization,
)
from app.db.models.registries.measurement_unit import MeasurementUnitRegistry
from app.db.models.registries.measurement_unit_localization import (
    MeasurementUnitRegistryLocalization,
)
from app.db.models.registries.placeholder import PlaceholderRegistry
from app.db.models.registries.placeholder_localization import PlaceholderRegistryLocalization
from app.db.models.registries.tax_id_system import TaxIdSystemRegistry
from app.db.models.registries.tax_id_system_localization import (
    TaxIdSystemRegistryLocalization,
)
from app.db.seed import Batch, Rows, SeedSpec

NAME_COLUMNS = {
    "ENG" : "name",
    "UKR" : "name_UKR",
    "DEU" : "name_DEU",
    "FRA" : "name_FRA",
    "POL" : "name_POL",
}

TAX_NAME_COLUMNS = NAME_COLUMNS | {
    "CES" : "name_CES",
    "EST" : "name_EST",
    "ITA" : "name_ITA",
    "LAV" : "name_LAV",
    "LIT" : "name_LIT",
    "NLD" : "name_NLD",
    "SLK" : "name_SLK",
    "SPA" : "name_SPA",
}


def _names(
        raw: Rows,
        fk_field: str,
        columns: dict[str, str],
) -> Rows:
    """One localization per row that actually has a translation"""

    return [
        { fk_field: r["code"], "language_code": language, "name": r[column] }
        for r in raw
        for language, column in columns.items()
        if r.get(column)
    ]


def _registry(
        model,
        localization_model,
        fk_field,
        columns,
):

    def expand(raw: Rows) -> Batch:
        parents = [
            { "code": r["code"], "system": r["system"], "active": r["active"] }
            for r in raw
        ]

        return (
            (model, parents),
            (localization_model, _names(raw, fk_field, columns)),
        )

    return expand


def expand_languages(raw: Rows) -> Batch:

    return (
        (Language, [
            {
                "code": r["ISO 639-3"].upper(),
                "code_alpha_2": r["ISO 639-1"],
                "label_en": r["ISO language name"],
                "label_uk": r["Ukrainian"],
            }
            for r in raw
        ]),
    )


def expand_countries(raw: Rows) -> Batch:

    countries = [ {"code": r["alpha-3"]} for r in raw ]

    localizations = [
        {"country_code": r["alpha-3"], "language_code": language, "name": r[column]}
        for r in raw
        for language, column in (("ENG", "name"), ("UKR", "name_UKR"))
        if r.get(column)
    ]

    return ((Country, countries), (CountryLocalization, localizations))


def expand_currencies(raw: Rows) -> Batch:

    currencies = [
        {
            "code": r["code"],
            "decimal_places": r["decimal_places"],
            "decimal_separator": r["decimal_separator"],
            "grouping_separator": r["grouping_separator"],
            "symbol_position": r["symbol_position"],
            "symbol_spacing": r["symbol_spacing"],
        }
        for r in raw
    ]

    localizations = [
        {
            "currency_code": r["code"],
            "language_code": language,
            "name": r[name_column],
            "symbol": r.get(symbol_column) or None,
        }
        for r in raw
        for language, name_column, symbol_column in (
            ("ENG", "name", "symbol"),
            ("UKR", "name_UKR", "symbol_UKR"),
        )
        if r.get(name_column)
    ]

    return ((Currency, currencies), (CurrencyLocalization, localizations))


def expand_document_types(raw: Rows) -> Batch:

    parents = [
        {"code": r["code"], "system": r["system"], "active": r["active"]}
        for r in raw
    ]

    columns = {
        "ENG": ("name", "description"),
        "UKR": ("name_UKR", "description_UKR"),
        "DEU": ("name_DEU", None),      # Currently only ENG & UKR seed tables carry descriptions,
        "FRA": ("name_FRA", None),      # edit if new descriptions added
        "POL": ("name_POL", None),
    }

    localizations = [
        {
            "document_type_code": r["code"],
            "language_code": language,
            "name": r[name_column],
            "description": (r.get(description_column) or None) if description_column else None,
        }
        for r in raw
        for language, (name_column, description_column) in columns.items()
        if r.get(name_column)
    ]

    return (
        (DocumentTypeRegistry, parents),
        (DocumentTypeRegistryLocalization, localizations),
    )


expand_measurement_units = _registry(
    MeasurementUnitRegistry, MeasurementUnitRegistryLocalization,
    "measurement_unit_code", TAX_NAME_COLUMNS,
)


expand_tax_id_system = _registry(
    TaxIdSystemRegistry, TaxIdSystemRegistryLocalization,
    "tax_id_system_code", TAX_NAME_COLUMNS,
)


def expand_placeholders(raw: Rows) -> Batch:

    parents = [
        {
            "key": r["key"],
            "system": r["system"],
            "required": r["required"],
            "type": r["type"],
            "active": r["active"],
            "columns": r["columns"],
        }
        for r in raw
    ]

    localizations = [
        {
            "placeholder_key": r["key"],
            "language_code": language,
            "label": r[label_column],
            "description": r.get(description_column) or None,
        }
        for r in raw
        for language, label_column, description_column in (
            ("ENG", "label", "description"),
            ("UKR", "label_UKR", "description_UKR"),
        )
        if r.get(label_column)
    ]

    return (
        (PlaceholderRegistry, parents),
        (PlaceholderRegistryLocalization, localizations),
    )


# (!) Languages always first
SEED_SPECS: tuple[SeedSpec, ...] = (
    SeedSpec("ISO Languages.json", expand_languages),
    SeedSpec("ISO Countries.json", expand_countries),
    SeedSpec("ISO Currencies.json", expand_currencies),
    SeedSpec("document_types.json", expand_document_types),
    SeedSpec("measurement_units.json", expand_measurement_units),
    SeedSpec("tax_id_systems.json", expand_tax_id_system),
    SeedSpec("placeholder.json", expand_placeholders),
)