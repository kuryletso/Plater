from dataclasses import dataclass
from zipfile import ZipFile, BadZipFile
from pathlib import Path
from os import PathLike

from lxml import etree

from app.document_engine.parser.errors import ParserFormatError


@dataclass(frozen=True)
class DocxPaths:
    document: str = "word/document.xml"
    styles: str = "word/styles.xml"
    numbering: str = "word/numbering.xml"
    relationships: str = "word/_rels/document.xml.rels"


class DocxArchive:
    def __init__(self, path: str | PathLike[str]) -> None:
        self.path = Path(path)

        try:
            self.zip = ZipFile(path)
        except BadZipFile as e:
            raise ParserFormatError(
                f"Not a valid .docx (unreadable zip archive): {self.path.name}."
            ) from e

    def __enter__(self):
        return self
    
    def __exit__(self, *_):
        self.close()

    _SAFE_PARSER = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
    )

    def read_xml(self, archive_path: str) -> etree._Element:
        try:
            data = self.zip.read(archive_path)
        except KeyError as e:
            raise ParserFormatError(
                f"Missing XML part: {archive_path}."
            ) from e
        
        try:
            return etree.fromstring(data, parser=self._SAFE_PARSER)
        except etree.XMLSyntaxError as e:
            raise ParserFormatError(
                f"Invalid XML in part: {archive_path}."
            ) from e
    
    def read_bytes(self, archive_path: str) -> bytes:
        try:
            return self.zip.read(archive_path)
        except KeyError as e:
            raise ParserFormatError(
                f"Missing XML part: {archive_path}."
            ) from e
    
    def get_uncompressed_size(self, archive_path: str) -> int:
        try:
            return self.zip.getinfo(archive_path).file_size
        except KeyError as e:
            raise ParserFormatError(
                f"Missing part: {archive_path}."
            ) from e

    def exists(self, archive_path: str) -> bool:
        return archive_path in self.zip.namelist()
    
    def close(self) -> None:
        self.zip.close()