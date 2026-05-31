import docx2txt
import io
import re
from docx import Document
from docx.oxml.ns import qn
import csv

class TextExtractor:
    """Extracts plain text from in-memory files loaded by GoogleDriveLoader, currently only supports .docx files."""
    def extract(self, result: dict) -> str:
        """Extracts text from a loaded file result.
        Args:
            result: dict returned by GoogleDriveLoader.load(), containing 'fh' and 'name'.
        Returns:
            Extracted text as a plain string.
        """
        fh = result["fh"]
        name = result["name"]
        if name.endswith(".docx"):
            return self._extract_docx(fh)
        elif name.endswith(".csv"):
            return self._extract_csv(fh)
        raise ValueError(f"Unsupported file type: {name}")

    def _extract_docx(self, fh: io.BytesIO) -> str:
        """Extracts text from a .docx file preserving the original order of paragraphs and tables.
        Paragraphs and tables are interleaved in document order.
        Table cells preserve internal line breaks from multiple paragraphs.
        """
        doc = Document(fh)
        output = []

        # Iterate over top-level blocks in the document body in order
        for block in doc.element.body:
            # Strip the XML namespace from the tag to get the plain tag name e.g. 'p' or 'tbl'
            tag = block.tag.split('}')[-1]

            if tag == 'p':
                # Collect all text fragments inside this paragraph
                # A paragraph can have multiple runs (w:r), each containing a text node (w:t)
                text = ''.join(
                    # find all <w:t> elements anywhere inside block, and take all the nodes' text
                    # .// means "search recursively anywhere inside this element"
                    # qn('w:t') resolves to the full namespaced XML tag for w:t
                    # or '' handles None text values on empty nodes
                    node.text or '' for node in block.findall('.//' + qn('w:t'))
                )
                # Only append if paragraph has actual content after stripping whitespace
                if text.strip():
                    output.append(text.strip())

            elif tag == 'tbl':
                table_rows = []

                for row in block.findall(qn('w:tr')):
                    cells = []
                    for cell in row.findall(qn('w:tc')):
                        paragraphs = []
                        for para in cell.findall(qn('w:p')):
                            para_text = ''.join(
                                node.text or '' for node in para.findall('.//' + qn('w:t'))
                            )
                            if para_text.strip():
                                paragraphs.append(para_text.strip())
                        cells.append('\n'.join(paragraphs))

                    if any(cells):
                        table_rows.append('| ' + ' | '.join(cells) + ' |')

                if table_rows:
                    output.append('[TABLE]')
                    output.extend(table_rows)
                    output.append('[/TABLE]')

        # Join all blocks with newlines to produce the final plain text output
        return '\n'.join(output)

    def _extract_csv(self, fh: io.BytesIO) -> str:
        """Extracts text from a CSV file as a Markdown table for LLM readability.
        Excludes columns with privacy-sensitive headers (phone, email, ID numbers).
        """
        try:
            text = fh.read().decode("utf-8")
        except UnicodeDecodeError:
            fh.seek(0)
            text = fh.read().decode("latin-1")

        reader = csv.reader(text.splitlines())
        rows = list(reader)

        if not rows:
            return ""

        # identify columns to exclude based on header name
        sensitive_keywords = {"telefoon", "telephone", "email", "nummer"}
        header = rows[0]
        excluded_indices = {
            i for i, col in enumerate(header)
            if any(keyword in col.lower() for keyword in sensitive_keywords)
        }

        def clean(value: str) -> str:
            # replace | to avoid breaking markdown table structure
            return value.replace("|", "/").strip()

        def filter_row(row: list) -> list:
            return [clean(val) for i, val in enumerate(row) if i not in excluded_indices]

        filtered_header = filter_row(header)
        lines = []
        lines.append("| " + " | ".join(filtered_header) + " |")
        lines.append("| " + " | ".join(["---"] * len(filtered_header)) + " |")

        for row in rows[1:]:
            # pad row to header length in case of missing trailing cells
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(filter_row(padded)) + " |")

        return "\n".join(lines)