# Authoring coverage matrix

> Generated from `edit.RECIPES` by `authoring_matrix.to_markdown()` — do not hand-edit; re-run the generator (or `GET /reference/authoring-matrix`) after adding a recipe.

**96 authoring recipes** across **15 categories**. Every recipe is a GUID-stable server-side pass. **What can invoke one differs per recipe**, and the Reach column says which: `cad+ai` — dispatchable from the CAD command line and the AI planner (12 of 96, the curated `nlauthor.RECIPE_SPECS`); `ui` — invoked by a tool panel, a router or MCP; `superseded` — nothing calls it and nothing should, a reachable recipe authors the same result; `none` — the engine can run it and no surface asks it to.

> ⚠ **12 recipes are reachable from no surface**: `add_connection_assembly`, `batch_tag`, `convert_length_unit`, `derive_representations`, `place_type`, `program_fit`, `purge_empty_groups`, `purge_orphan_psets`, `rebase_origin`, `reset_prop_to_type`, `resolve_wall_joins`, `set_spec_link`. They are implemented and tested; they are not something a user can invoke, so they are not coverage. Pinned by `services/api/test_recipe_reach.py`.

> **Superseded** — uncalled, and correctly so: `add_sprinkler` → `add_fire_equipment`. A reachable recipe authors the identical result, so these are duplicate spellings rather than gaps. The equivalence is asserted in `services/api/test_recipe_reach.py`, so an entry stops being true if the two recipes stop agreeing.

### create-structure (13)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `add_base_plate` | IfcPlate (base plate) | ui |
| `add_beam` | IfcBeam | cad+ai |
| `add_column` | IfcColumn | cad+ai |
| `add_connection_assembly` | connection plate+bolts + IfcRelConnectsWithRealizingElements | none |
| `add_footing` | IfcFooting | ui |
| `add_rebar` | IfcReinforcingBar | ui |
| `add_rebar_cage` | IfcReinforcingBar (cage) | ui |
| `add_shear_tab` | IfcPlate (shear tab) + bolts | ui |
| `add_slab` | IfcSlab | ui |
| `add_steel_beam` | IfcBeam (steel profile) | cad+ai |
| `add_steel_column` | IfcColumn (steel profile) | cad+ai |
| `add_wall` | IfcWall | cad+ai |
| `extrude_profile` | sketch profile → extruded element | ui |

### create-enclosure (7)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `add_covering` | IfcCovering | ui |
| `add_curtain_wall` | IfcCurtainWall | cad+ai |
| `add_railing` | IfcRailing | ui |
| `add_ramp` | IfcRamp | ui |
| `add_roof` | IfcRoof | ui |
| `add_roof_window` | IfcWindow (SKYLIGHT) voiding a roof | ui |
| `add_stair` | IfcStair | ui |

### create-opening (2)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `add_door` | IfcDoor + IfcOpeningElement | cad+ai |
| `add_window` | IfcWindow + IfcOpeningElement | cad+ai |

### create-space (2)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `add_spaces` | IfcSpace (per storey) | cad+ai |
| `add_storey` | IfcBuildingStorey | ui |

### create-mep (11)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `add_cable_tray` | IfcCableCarrierSegment | ui |
| `add_comms_device` | telecom device | ui |
| `add_duct` | IfcDuctSegment | ui |
| `add_fa_device` | fire-alarm device | ui |
| `add_fire_equipment` | fire-protection equipment | ui |
| `add_mep_fitting` | IfcDuct/PipeFitting | ui |
| `add_mep_terminal` | IfcDuct/PipeTerminal | ui |
| `add_pipe` | IfcPipeSegment | ui |
| `add_riser` | vertical MEP riser | ui |
| `add_sprinkler` | IfcFireSuppressionTerminal | superseded |
| `add_wire` | IfcCableSegment | ui |

### create-content (5)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `add_family` | family occurrence | ui |
| `add_mesh_representation` | IfcBuildingElementProxy (mesh) | ui |
| `furnish_spaces` | FF&E per room | ui |
| `place_content` | catalog content | ui |
| `program_fit` | headcount program → zones + seats | none |

### annotate (4)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `add_annotation` | IfcAnnotation (text) | ui |
| `add_dimension` | IfcAnnotation (dimension) | ui |
| `add_revision_cloud` | IfcAnnotation (rev cloud) | ui |
| `add_tag` | IfcAnnotation (element tag) | ui |

### edit (13)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `connect_elements` | IfcRelConnectsElements | ui |
| `copy_element` | duplicate | ui |
| `delete_element` | remove | cad+ai |
| `execute_ifc_code` | sandboxed ifcopenshell escape hatch | ui |
| `move_element` | translate | ui |
| `rename_storey` | rename level | ui |
| `resolve_wall_joins` | butt-join L/T wall joins | none |
| `rotate_element` | rotate | ui |
| `set_extrusion_depth` | push/pull an extrusion depth | ui |
| `set_profile_dims` | resize an extruded profile in place | ui |
| `set_storey_elevation` | move level | ui |
| `set_wall_slope` | sloped-top wall | ui |
| `set_wall_thickness` | wall thickness (profile XDim sugar) | ui |

### edit-mep (3)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `auto_connect_mep` | coincident-port auto-connect sweep | ui |
| `connect_mep` | port-to-port connection | ui |
| `set_system_predefined` | system predefined type | ui |

### type (3)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `create_type` | IfcTypeProduct | ui |
| `edit_type_params` | edit type parameters | ui |
| `place_type` | type occurrence | none |

### group (5)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `array_element` | linear/grid array | ui |
| `create_assembly` | IfcElementAssembly | ui |
| `create_group` | IfcGroup | ui |
| `set_array_params` | re-edit a placed array's count/pitch | ui |
| `ungroup` | dissolve a group | ui |

### data (18)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `apply_detailing_rules` | rule-driven details | ui |
| `apply_layers` | property-override layers | ui |
| `assign_material_set` | IfcMaterialLayerSet | ui |
| `attach_document` | IfcRelAssociatesDocument | ui |
| `attach_om_document` | O&M document ref | ui |
| `batch_tag` | AEC_Tags label | none |
| `classify` | IfcClassificationReference | ui |
| `derive_representations` | coarse Box/Axis/FootPrint views | none |
| `ensure_contexts` | representation contexts | ui |
| `map_properties` | vendor→IDS pset remap | ui |
| `reset_prop_to_type` | Reset property to type | none |
| `set_classification` | classification | ui |
| `set_element_pset` | Pset property | ui |
| `set_lod` | LOD stage tag | cad+ai |
| `set_manufacturer_info` | manufacturer psets | ui |
| `set_props_by_guid` | Pset batch (XLSX round-trip) | ui |
| `set_pset` | Pset property | ui |
| `set_spec_link` | Pset_Massing_SpecLink breadcrumb | none |

### lifecycle (3)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `record_asbuilt_dimension` | as-built dimension | ui |
| `set_phase` | Massing_Phasing.Status | cad+ai |
| `verify_asbuilt` | LOD-500 verified | ui |

### analysis (3)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `apply_structural_loads` | IfcStructuralLoad | ui |
| `apply_structural_supports` | IfcStructuralConnection | ui |
| `derive_analytical` | IfcStructuralAnalysisModel | ui |

### maintenance (4)

| Recipe | Produces | Reach |
| --- | --- | --- |
| `convert_length_unit` | convert the project length unit | none |
| `purge_empty_groups` | purge empty groups | none |
| `purge_orphan_psets` | purge orphaned property sets | none |
| `rebase_origin` | shift model origin (georeference-preserving) | none |

