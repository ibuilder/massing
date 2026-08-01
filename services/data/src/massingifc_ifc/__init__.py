"""``massingifc_ifc`` — IFC to scene package, using IfcOpenShell.

Split from ``massingifc_scene`` so the reader half stays dependency-free: an engine importer or a
CI check should not have to install an IFC toolkit to open a package.
"""

from .audit import FidelityIssue, FidelityReport, audit_conversion
from .convert import UnknownUnitError, convert_ifc

__all__ = [
    "FidelityIssue",
    "FidelityReport",
    "UnknownUnitError",
    "audit_conversion",
    "convert_ifc",
]
