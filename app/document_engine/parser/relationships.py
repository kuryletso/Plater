from typing import TYPE_CHECKING

from dataclasses import dataclass
from pathlib import PurePosixPath

from lxml.etree import _Element

from app.document_engine.parser.archive import DocxArchive
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.errors import ParserSecurityError, ParserFormatError


PACKAGE_ROOT = PurePosixPath("word")


@dataclass(slots=True)
class Relationship:
    id: str
    type: str
    target: str
    is_external: bool


class RelationshipResolver:
    def __init__(
            self,
            relationships_root: _Element | None,
            base: PurePosixPath = PACKAGE_ROOT,
    ) -> None:
        """`base` is the directory of the part these relationships belong to.
        Relative targets resolve aginst it.
        """

        self._relationships: dict[str, Relationship] = {}

        if relationships_root is None:
            return

        for relationship in relationships_root.findall("pr:Relationship", NS):
            relationship_id = relationship.get("Id")
            relationship_type = relationship.get("Type")
            target = relationship.get("Target")

            if relationship_id is None \
            or relationship_type is None \
            or target is None:
                continue

            target_mode = relationship.get("TargetMode")
            is_external = target_mode == "External"

            normalized_target = (
                target
                if is_external
                else self._normalize_target(target, base)
            )

            self._relationships[relationship_id] = Relationship(
                id=relationship_id,
                type=relationship_type,
                target=normalized_target,
                is_external=is_external,
            )

    def get(self, relationship_id: str) -> Relationship | None:
        return self._relationships.get(relationship_id)


    @staticmethod
    def _normalize_target(target: str, base: PurePosixPath = PACKAGE_ROOT) -> str:
        path = PurePosixPath(target)
        if path.is_absolute():
            raise ParserSecurityError(
                f"Invalid relationship path: {target}."
            )

        resolved: list[str] = []
        for part in (base / path).parts:
            if part == "..":
                if not resolved:
                    raise ParserSecurityError(
                        f"Invalid relationship path: {target}."
                    )
                resolved.pop()
            else:
                resolved.append(part)

        return str(PurePosixPath(*resolved))


def rels_path(part: str) -> str:
    """The relationships part that belongs to a package part: 
    'word/footer1.xml' -> 'word/_rels/footer1.xml.rels'.
    """

    path = PurePosixPath(part)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def part_relationships(archive: DocxArchive, part: str) -> RelationshipResolver:
    """Relationships of one package part, resolved against that part's directory.
    
    Every part has its own relationship table — a footer's rId1 is not the 
    document's rId1. Part without a relationship file is valid and has none.
    """

    try:
        root = archive.read_xml(rels_path(part))
    except ParserFormatError:
        root = None

    return RelationshipResolver(root, base=PurePosixPath(part).parent)