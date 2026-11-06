"""Patch native Excel data without discarding tables or workbook metadata."""
from __future__ import annotations

import posixpath
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from xml.parsers import expat
from zipfile import BadZipFile, ZipFile
from xml.sax.saxutils import quoteattr

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"s": MAIN}
_INTEGRITY_CACHE = {}


def related_part(part, target):
    return target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def relationships_part(part):
    parent, name = posixpath.split(part)
    return posixpath.join(parent, "_rels", name + ".rels")


def _cell_text(cell, shared):
    if cell is None:
        return ""
    if cell.get("t") == "inlineStr":
        return "".join(cell.find("s:is", NS).itertext())
    value = cell.find("s:v", NS)
    if value is None or value.text is None:
        return ""
    return shared[int(value.text)] if cell.get("t") == "s" else value.text


def workbook_errors(path: Path) -> list[str]:
    try:
        with Path(path).open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest in _INTEGRITY_CACHE:
            return list(_INTEGRITY_CACHE[digest])
        errors = _workbook_errors(path)
        if len(_INTEGRITY_CACHE) >= 64:
            _INTEGRITY_CACHE.pop(next(iter(_INTEGRITY_CACHE)))
        _INTEGRITY_CACHE[digest] = tuple(errors)
        return errors
    except (BadZipFile, ET.ParseError, expat.ExpatError, KeyError, ValueError, TypeError) as error:
        return [f"invalid Excel package: {error}"]


def _workbook_errors(path: Path) -> list[str]:
    """Check XML, ZIP integrity and Excel table links that pandas ignores."""
    errors = []
    with ZipFile(path) as book:
        bad = book.testzip()
        if bad:
            errors.append(f"invalid ZIP checksum: {bad}")
        names = book.namelist()
        if len(names) != len(set(names)):
            errors.append("duplicate ZIP members")
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = ["".join(item.itertext()) for item in ET.fromstring(book.read("xl/sharedStrings.xml"))]
        styles = ET.fromstring(book.read("xl/styles.xml")).find("s:cellXfs", NS)
        for part in names:
            if not part.startswith("xl/worksheets/") or not part.endswith(".xml") or "/_rels/" in part:
                continue
            relationships = relationships_part(part)
            table_links = {}
            if relationships in names:
                table_links = {r.get("Id"): related_part(part, r.get("Target"))
                               for r in ET.fromstring(book.read(relationships)) if r.get("Type", "").endswith("/table")}
            tables = {}
            addresses = set()
            for table_part in table_links.values():
                if table_part not in names:
                    errors.append(f"{part}: missing table part {table_part}")
                    continue
                table = ET.fromstring(book.read(table_part))
                from openpyxl.utils.cell import range_boundaries, get_column_letter
                left, top, right, _ = range_boundaries(table.get("ref"))
                if table.get("headerRowCount", "1") == "0":
                    continue
                columns = table.find("s:tableColumns", NS)
                if len(columns) != right - left + 1:
                    errors.append(f"{table_part}: table width differs from column count")
                    continue
                tables[table_part] = {f"{get_column_letter(index)}{top}": column.get("name")
                                      for index, column in enumerate(columns, start=left)}
                addresses.update(tables[table_part])
            with book.open(part) as source:
                references, values, invalid_style = _worksheet_metadata(source, addresses, shared, len(styles))
            if invalid_style:
                errors.append(f"{part}: invalid cell style")
            if references != set(table_links):
                errors.append(f"{part}: worksheet/table relationships disagree")
            for table_part, headers in tables.items():
                for address, expected in headers.items():
                    if values.get(address, "") != expected:
                        errors.append(f"{table_part}: table header disagrees with {address}")
    return errors


def _worksheet_metadata(source, addresses, shared, style_count):
    """Inspect a worksheet with bounded buffers, retaining table headers only."""
    cell_tag, value_tag, text_tag = (MAIN + "}" + tag for tag in ("c", "v", "t"))
    table_tag = MAIN + "}tablePart"
    references, values = set(), {}
    state = dict(address=None, kind=None, text=[], capture=False, invalid_style=False)
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    pending = set(addresses)

    def start(name, attrs):
        if name == cell_tag:
            style = attrs.get("s")
            if style is not None and int(style) >= style_count:
                state["invalid_style"] = True
            if not pending:
                return
            address = attrs.get("r")
            state["address"] = address if address in pending else None
            state["kind"] = attrs.get("t")
            state["text"] = []
        elif state["address"] is not None and name in (value_tag, text_tag):
            state["capture"] = True
        elif name == table_tag:
            references.add(attrs.get(REL + "}id"))

    def end(name):
        if name in (value_tag, text_tag):
            state["capture"] = False
        elif name == cell_tag and state["address"] is not None:
            value = "".join(state["text"])
            if state["kind"] == "s" and value:
                value = shared[int(value)]
            values[state["address"]] = value
            pending.discard(state["address"])
            state["address"] = None
            if not pending:
                parser.EndElementHandler = None
                parser.CharacterDataHandler = None

    def chars(value):
        if state["capture"]:
            state["text"].append(value)

    parser.StartElementHandler = start
    parser.EndElementHandler = end if pending else None
    parser.CharacterDataHandler = chars if pending else None
    while chunk := source.read(1024 * 1024):
        parser.Parse(chunk, False)
    parser.Parse(b"", True)
    return references, values, state["invalid_style"]


def _tag_end(payload, start):
    """End of one XML tag, allowing greater-than signs inside quoted attributes."""
    quote = None
    for index in range(start, len(payload)):
        char = payload[index]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in (34, 39):
            quote = char
        elif char == 62:
            return index + 1
    raise ValueError("Unterminated XML tag")


def _sheet_content(payload, name, role):
    """Locate native data by expanded XML name without building a cell tree.

    Expat byte offsets let us preserve every unrelated byte, including cached
    formulas, declarations, decorations and worksheet/table relationships.
    """
    parser = expat.ParserCreate(namespace_separator="}")
    bindings, previous, dimensions = {}, {}, []
    state = dict(depth=0)

    class Complete(Exception):
        pass

    def namespace_start(prefix, uri):
        prefix = prefix or ""
        previous.setdefault(prefix, []).append(bindings.get(prefix))
        bindings[prefix] = uri or ""

    def namespace_end(prefix):
        prefix = prefix or ""
        value = previous[prefix].pop()
        if value is None:
            bindings.pop(prefix, None)
        else:
            bindings[prefix] = value

    def end_before_data(tag):
        state['depth'] -= 1

    def finish(tag):
        if tag == MAIN + "}sheetData":
            state['end'] = state['opening_end'] if state['empty'] else _tag_end(payload, parser.CurrentByteIndex)
            raise Complete()

    def start(tag, attrs):
        state['depth'] += 1
        if state['depth'] != 2:
            return
        if tag == MAIN + "}dimension":
            offset = parser.CurrentByteIndex
            dimensions.append((offset, _tag_end(payload, offset)))
        elif tag == MAIN + "}sheetData":
            offset = parser.CurrentByteIndex
            opening_end = _tag_end(payload, offset)
            state.update(start=offset, opening_end=opening_end,
                         empty=payload[offset:opening_end].endswith(b'/>'), namespaces=dict(bindings))
            parser.StartElementHandler = None
            parser.StartNamespaceDeclHandler = None
            parser.EndNamespaceDeclHandler = None
            parser.EndElementHandler = finish

    parser.StartNamespaceDeclHandler = namespace_start
    parser.EndNamespaceDeclHandler = namespace_end
    parser.StartElementHandler = start
    parser.EndElementHandler = end_before_data
    try:
        parser.Parse(payload, True)
    except Complete:
        return state['start'], state['end'], state['namespaces'], dimensions
    except expat.ExpatError as error:
        raise ValueError(f"Invalid {role} worksheet XML in {name}: {error}") from error
    raise ValueError(f"Cannot locate {role} sheet data in {name}")


def _local_namespace_data(data, bindings):
    """Carry the replacement's namespace context into any target tag style."""
    end = _tag_end(data, 0)
    opening = data[:end]
    declared = {match.group(1).decode() if match.group(1) else ''
                for match in re.finditer(rb'\sxmlns(?::([A-Za-z_][A-Za-z0-9_.-]*))?\s*=', opening)}
    # An explicitly empty default namespace also protects a prefixed source
    # subtree from accidentally inheriting the target's default namespace.
    bindings = {'': '', **bindings}
    additions = ''.join(' xmlns' + (':' + prefix if prefix else '') + '=' + quoteattr(uri)
                        for prefix, uri in bindings.items() if prefix not in declared).encode('utf-8')
    insert = end - (2 if opening.endswith(b'/>') else 1)
    return data[:insert] + additions + data[insert:]


def patch_sheet_parts(original: ZipFile, replacement: ZipFile, original_paths, new_paths, frames):
    """Preserve worksheet relationships and decorations around new sheet data."""
    from openpyxl.utils.cell import range_boundaries, get_column_letter
    patches = {}
    for name, frame in frames.items():
        part = original_paths[name]
        payload = original.read(part)
        incoming = replacement.read(new_paths[name])
        start, end, _, dimensions = _sheet_content(payload, name, 'native')
        new_start, new_end, bindings, _ = _sheet_content(incoming, name, 'replacement')
        data = _local_namespace_data(incoming[new_start:new_end], bindings)
        extent = f'A1:{get_column_letter(max(1, len(frame.columns)))}{len(frame) + 1}'
        edits = [(start, end, data)]
        for left, right in dimensions:
            opening = payload[left:right]
            ref = rb'''\bref\s*=\s*(?:"[^"]*"|'[^']*')'''
            if re.search(ref, opening):
                opening = re.sub(ref, lambda _: f'ref="{extent}"'.encode(), opening, count=1)
            else:
                insert = len(opening) - (2 if opening.endswith(b'/>') else 1)
                opening = opening[:insert] + f' ref="{extent}"'.encode() + opening[insert:]
            edits.append((left, right, opening))
        for left, right, value in sorted(edits, reverse=True):
            payload = payload[:left] + value + payload[right:]
        patches[part] = payload
        rels = relationships_part(part)
        if rels not in original.namelist():
            continue
        for relationship in ET.fromstring(original.read(rels)):
            if not relationship.get("Type", "").endswith("/table"):
                continue
            table_part = related_part(part, relationship.get("Target"))
            table = ET.fromstring(original.read(table_part))
            left, top, right, _ = range_boundaries(table.get("ref"))
            if top != 1 or right > len(frame.columns) or frame.empty:
                raise ValueError(f"Replacement {name} cannot preserve table {table.get('name')}")
            table.set("ref", f"{get_column_letter(left)}1:{get_column_letter(right)}{len(frame) + 1}")
            auto_filter = table.find("s:autoFilter", NS)
            if auto_filter is not None:
                auto_filter.set("ref", table.get("ref"))
            columns = table.find("s:tableColumns", NS)
            for index, column in enumerate(columns, start=left - 1):
                column.set("name", str(frame.columns[index]))
            patches[table_part] = ET.tostring(table, encoding="utf-8", xml_declaration=True)
    return patches
