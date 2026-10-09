"""Keep JUnit outcomes and source locations, never payloads or captured logs."""

import re
from pathlib import Path
from xml.etree import ElementTree as ET


def sanitize_reports(directory):
    for path in Path(directory).glob("*.xml"):
        root = ET.parse(path).getroot()
        for parent in root.iter():
            for child in list(parent):
                if child.tag in ("system-out", "system-err", "properties"):
                    parent.remove(child)
                elif child.tag in ("failure", "error", "skipped"):
                    locations = sorted(
                        set(re.findall(r"[A-Za-z0-9_./-]+\.py:\d+", child.text or ""))
                    )
                    child.attrib.clear()
                    child.set(
                        "message",
                        "Details withheld; see test name and source locations",
                    )
                    child.text = "\n".join(locations)
        ET.ElementTree(root).write(path, encoding="unicode")
