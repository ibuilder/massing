"""Conversion fidelity: does the package contain what the IFC contained?

This answers a question nothing else here asks. The conformance suite checks that the *format*
round-trips between two implementations — but both would agree perfectly on a package that is
missing a wall. The converter's own tests check specific behaviours, which only ever covers the
behaviours somebody thought to write down. Between them sat the two bugs that shipped: elements
dropped without a word, and property sets colliding.

So these checks compare the package against the source file directly, and they are deliberately
derived from the IFC rather than from the converter's own traversal. Re-walking the spatial tree
the same way the converter does would only prove the walk agrees with itself; asking each element
which structure *it* says contains it is an independent question.

Public rather than test-only on purpose. The useful moment for this is somebody converting a real
project and wanting to know what did not survive, which is exactly when a hand-written fixture has
nothing to say.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from massingifc_scene import ScenePackage, ScenePackageError, SceneImporter


@dataclass(frozen=True)
class FidelityIssue:
    severity: str
    code: str
    message: str
    subject: Optional[str] = None


@dataclass(frozen=True)
class FidelityReport:
    """What survived conversion, and what did not."""

    faithful: bool
    issues: Sequence[FidelityIssue]
    products_in_source: int
    #: Products from the source that reached the package — not the node count, which is larger.
    #: A package also carries `IfcProject`, which is a context rather than a product, so comparing
    #: node count against product count would read as more arriving than went in.
    products_in_package: int
    nodes_in_package: int

    @property
    def errors(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def summary(self) -> str:
        return (
            f"{self.products_in_package}/{self.products_in_source} products in the package, "
            f"{self.errors} error(s), {self.warnings} warning(s)"
        )


def _spatial_container(product: Any) -> Optional[str]:
    """The GlobalId of whatever the *source file* says contains this product.

    Read from the element's own inverse relationships rather than by walking down from the project,
    so the answer does not depend on the traversal being audited.
    """
    for relation in getattr(product, "ContainedInStructure", None) or ():
        structure = getattr(relation, "RelatingStructure", None)
        if structure is not None and getattr(structure, "GlobalId", None):
            return structure.GlobalId
    for relation in getattr(product, "Decomposes", None) or ():
        whole = getattr(relation, "RelatingObject", None)
        if whole is not None and getattr(whole, "GlobalId", None):
            return whole.GlobalId
    return None


def _has_property_definitions(product: Any) -> bool:
    for relation in getattr(product, "IsDefinedBy", None) or ():
        definition = getattr(relation, "RelatingPropertyDefinition", None)
        if definition is None:
            continue
        if getattr(definition, "HasProperties", None) or getattr(definition, "Quantities", None):
            return True
    return False


def audit_conversion(source: Path | str | Any, scene: ScenePackage) -> FidelityReport:
    """Compare a converted package against the IFC it came from.

    `source` is a path or an already-opened ifcopenshell file.
    """
    try:
        import ifcopenshell  # noqa: PLC0415 - only this function needs it
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ScenePackageError("Auditing a conversion needs ifcopenshell.") from exc

    ifc_file = source if hasattr(source, "by_type") else ifcopenshell.open(str(Path(source)))

    from .convert import is_excluded

    # Voids and ports are products, and are deliberately not scene nodes. Counting them as losses
    # would report 47 missing elements on a house that converted perfectly — and a warning that
    # fires when nothing is wrong is one nobody reads when something is.
    products = [
        product
        for product in ifc_file.by_type("IfcProduct")
        if getattr(product, "GlobalId", None) and not is_excluded(product)
    ]
    importer = SceneImporter(scene, check_index=False)
    issues: List[FidelityIssue] = []

    # 1. Accounting. Every product is either in the package or is not, and the count is stated
    #    rather than left to be noticed. A missing element is sometimes legitimate — an orphan, or
    #    a scoped export — so this is a warning; being silent about it is what is not acceptable.
    missing = [product for product in products if product.GlobalId not in importer]
    if missing:
        sample = ", ".join(f"{p.is_a()} {p.GlobalId}" for p in missing[:5])
        issues.append(
            FidelityIssue(
                "warning",
                "product-not-in-package",
                f"{len(missing)} of {len(products)} products did not reach the package: {sample}"
                + (" ..." if len(missing) > 5 else ""),
            )
        )

    present = [product for product in products if product.GlobalId in importer]

    # 2. Class counts, over the products that did arrive. A count that disagrees means the class
    #    index is wrong even though every element is present — an element that cannot be found by
    #    the filter an engine actually uses might as well be absent.
    source_counts: Dict[str, int] = {}
    for product in present:
        source_counts[product.is_a().upper()] = source_counts.get(product.is_a().upper(), 0) + 1
    for ifc_class, expected in sorted(source_counts.items()):
        actual = len(importer.by_class(ifc_class))
        if actual != expected:
            issues.append(
                FidelityIssue(
                    "error",
                    "class-count-mismatch",
                    f"{ifc_class}: {expected} in the file, {actual} in the class index.",
                    ifc_class,
                )
            )

    # 3. Semantics. An element that carried property sets in the file and carries none in the
    #    package lost them somewhere, which is the quietest possible failure: the element is still
    #    selectable, still the right shape, and simply knows nothing about itself.
    if scene.properties is not None:
        lost = [
            product
            for product in present
            if _has_property_definitions(product) and not importer.property_sets(product.GlobalId)
        ]
        if lost:
            sample = ", ".join(product.GlobalId for product in lost[:5])
            issues.append(
                FidelityIssue(
                    "error",
                    "properties-lost",
                    f"{len(lost)} product(s) had property sets in the file and none in the "
                    f"package: {sample}" + (" ..." if len(lost) > 5 else ""),
                )
            )

    # 4. Containment, asked of each element rather than re-derived by walking down. If the file
    #    says a wall sits in a storey, that storey has to appear somewhere above the wall in the
    #    package — otherwise level filtering and the spatial tree are quietly wrong.
    for product in present:
        container = _spatial_container(product)
        if container is None or container not in importer:
            continue
        ancestors = {node.global_id for node in importer.ancestors(product.GlobalId)}
        if container not in ancestors:
            issues.append(
                FidelityIssue(
                    "error",
                    "containment-lost",
                    f"The file places {product.GlobalId} inside {container}, which is not among "
                    "its ancestors in the package.",
                    product.GlobalId,
                )
            )

    return FidelityReport(
        faithful=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        products_in_source=len(products),
        products_in_package=len(present),
        nodes_in_package=len(importer),
    )
