# Authoring coverage matrix

> Generated from `edit.RECIPES` by `authoring_matrix.to_markdown()` — do not hand-edit; re-run the generator (or `GET /reference/authoring-matrix`) after adding a recipe.

**88 authoring recipes** across **15 categories**. Every recipe is a GUID-stable server-side pass, dispatchable from the CAD command line, the AI command bar, the node canvas, or the tool panels.

### create-structure (13)

| Recipe | Produces |
| --- | --- |
| `add_base_plate` | IfcPlate (base plate) |
| `add_beam` | IfcBeam |
| `add_column` | IfcColumn |
| `add_connection_assembly` | connection plate+bolts + IfcRelConnectsWithRealizingElements |
| `add_footing` | IfcFooting |
| `add_rebar` | IfcReinforcingBar |
| `add_rebar_cage` | IfcReinforcingBar (cage) |
| `add_shear_tab` | IfcPlate (shear tab) + bolts |
| `add_slab` | IfcSlab |
| `add_steel_beam` | IfcBeam (steel profile) |
| `add_steel_column` | IfcColumn (steel profile) |
| `add_wall` | IfcWall |
| `extrude_profile` | sketch profile → extruded element |

### create-enclosure (5)

| Recipe | Produces |
| --- | --- |
| `add_covering` | IfcCovering |
| `add_curtain_wall` | IfcCurtainWall |
| `add_railing` | IfcRailing |
| `add_roof` | IfcRoof |
| `add_roof_window` | IfcWindow (SKYLIGHT) voiding a roof |

### create-opening (2)

| Recipe | Produces |
| --- | --- |
| `add_door` | IfcDoor + IfcOpeningElement |
| `add_window` | IfcWindow + IfcOpeningElement |

### create-space (2)

| Recipe | Produces |
| --- | --- |
| `add_spaces` | IfcSpace (per storey) |
| `add_storey` | IfcBuildingStorey |

### create-mep (11)

| Recipe | Produces |
| --- | --- |
| `add_cable_tray` | IfcCableCarrierSegment |
| `add_comms_device` | telecom device |
| `add_duct` | IfcDuctSegment |
| `add_fa_device` | fire-alarm device |
| `add_fire_equipment` | fire-protection equipment |
| `add_mep_fitting` | IfcDuct/PipeFitting |
| `add_mep_terminal` | IfcDuct/PipeTerminal |
| `add_pipe` | IfcPipeSegment |
| `add_riser` | vertical MEP riser |
| `add_sprinkler` | IfcFireSuppressionTerminal |
| `add_wire` | IfcCableSegment |

### create-content (5)

| Recipe | Produces |
| --- | --- |
| `add_family` | family occurrence |
| `add_mesh_representation` | IfcBuildingElementProxy (mesh) |
| `furnish_spaces` | FF&E per room |
| `place_content` | catalog content |
| `program_fit` | headcount program → zones + seats |

### annotate (4)

| Recipe | Produces |
| --- | --- |
| `add_annotation` | IfcAnnotation (text) |
| `add_dimension` | IfcAnnotation (dimension) |
| `add_revision_cloud` | IfcAnnotation (rev cloud) |
| `add_tag` | IfcAnnotation (element tag) |

### edit (10)

| Recipe | Produces |
| --- | --- |
| `connect_elements` | IfcRelConnectsElements |
| `copy_element` | duplicate |
| `delete_element` | remove |
| `execute_ifc_code` | sandboxed ifcopenshell escape hatch |
| `move_element` | translate |
| `rename_storey` | rename level |
| `rotate_element` | rotate |
| `set_extrusion_depth` | push/pull an extrusion depth |
| `set_storey_elevation` | move level |
| `set_wall_slope` | sloped-top wall |

### edit-mep (3)

| Recipe | Produces |
| --- | --- |
| `auto_connect_mep` | coincident-port auto-connect sweep |
| `connect_mep` | port-to-port connection |
| `set_system_predefined` | system predefined type |

### type (3)

| Recipe | Produces |
| --- | --- |
| `create_type` | IfcTypeProduct |
| `edit_type_params` | edit type parameters |
| `place_type` | type occurrence |

### group (4)

| Recipe | Produces |
| --- | --- |
| `array_element` | linear/grid array |
| `create_assembly` | IfcElementAssembly |
| `create_group` | IfcGroup |
| `ungroup` | dissolve a group |

### data (18)

| Recipe | Produces |
| --- | --- |
| `apply_detailing_rules` | rule-driven details |
| `apply_layers` | property-override layers |
| `assign_material_set` | IfcMaterialLayerSet |
| `attach_document` | IfcRelAssociatesDocument |
| `attach_om_document` | O&M document ref |
| `batch_tag` | AEC_Tags label |
| `classify` | IfcClassificationReference |
| `derive_representations` | coarse Box/Axis/FootPrint views |
| `ensure_contexts` | representation contexts |
| `map_properties` | vendor→IDS pset remap |
| `reset_prop_to_type` | Reset property to type |
| `set_classification` | classification |
| `set_element_pset` | Pset property |
| `set_lod` | LOD stage tag |
| `set_manufacturer_info` | manufacturer psets |
| `set_props_by_guid` | Pset batch (XLSX round-trip) |
| `set_pset` | Pset property |
| `set_spec_link` | Pset_Massing_SpecLink breadcrumb |

### lifecycle (3)

| Recipe | Produces |
| --- | --- |
| `record_asbuilt_dimension` | as-built dimension |
| `set_phase` | Massing_Phasing.Status |
| `verify_asbuilt` | LOD-500 verified |

### analysis (3)

| Recipe | Produces |
| --- | --- |
| `apply_structural_loads` | IfcStructuralLoad |
| `apply_structural_supports` | IfcStructuralConnection |
| `derive_analytical` | IfcStructuralAnalysisModel |

### maintenance (2)

| Recipe | Produces |
| --- | --- |
| `purge_empty_groups` | purge empty groups |
| `purge_orphan_psets` | purge orphaned property sets |
