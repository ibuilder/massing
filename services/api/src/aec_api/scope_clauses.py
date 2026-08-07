"""Scope-of-work clause library — the data behind `scope_library`.

Generated from the ScopeMaker seed library (ibuilder/procore-exhibit-generator), which is
the user's own work. DO NOT hand-edit for bulk changes: regenerate. Small corrections in
place are fine and expected — this is a starter library, not a spec.

Shape, and why it differs from the source: ScopeMaker clauses carry no `title`, only `text`,
so `title` is derived from the last segment of the dotted key — stable across regeneration,
which a title derived from the body text would not be. Categories are mapped to the Title
Case vocabulary `contracts.py` already filters on; `inclusion` becomes `Scope` so that an
inclusion lands in Exhibit A and stays OUT of the agreement body, which is what that filter
is for.

`division` is a CSI MasterFormat division number, or None for a universal clause.
"""
from __future__ import annotations

from typing import Any

CLAUSES: list[dict[str, Any]] = [
    {"id": "univ.gen.division01", "division": None, "category": "General Conditions",
     "title": "Division 01", "default": True, "position": 10,
     "body": "Subcontractor shall comply with all Division 01 General Requirements, the Project Manual, the General "
             "Conditions and Supplementary Conditions, and all Project-specific procedures issued by the Contractor."
     },
    {"id": "univ.gen.site_logistics", "division": None, "category": "General Conditions",
     "title": "Site Logistics", "default": True, "position": 20,
     "body": "Subcontractor shall comply with the Project site logistics plan, including designated laydown and "
             "staging areas, delivery windows, crane and hoist scheduling, parking restrictions, badging and site "
             "access procedures."
     },
    {"id": "univ.gen.meetings", "division": None, "category": "General Conditions",
     "title": "Meetings", "default": True, "position": 30,
     "body": "Subcontractor shall attend and actively participate in pre-construction, weekly coordination, safety, "
             "quality, look-ahead scheduling and progress meetings, and shall send a representative empowered to make "
             "binding commitments on behalf of the Subcontractor."
     },
    {"id": "univ.gen.supervision", "division": None, "category": "General Conditions",
     "title": "Supervision", "default": True, "position": 40,
     "body": "Subcontractor shall provide a competent, full-time, on-site supervisor who is fluent in English, is "
             "authorized to act on the Subcontractor's behalf, and remains assigned to the Project for its duration "
             "absent the Contractor's written consent to a replacement."
     },
    {"id": "univ.incl.complete_installation", "division": None, "category": "Scope",
     "title": "Complete Installation", "default": True, "position": 100,
     "body": "All labor, material, equipment, tools, consumables, supervision, transportation, hoisting, rigging, "
             "scaffolding, lifts, fuel, licenses, permits specific to this trade, burden, taxes and insurance required "
             "for a complete, operational and code-compliant installation."
     },
    {"id": "univ.incl.submittals", "division": None, "category": "Scope",
     "title": "Submittals", "default": True, "position": 110,
     "body": "Preparation and timely submission of all shop drawings, product data, samples, mock-ups, certifications "
             "and calculations required by the Contract Documents, including resubmittals required to obtain approval. "
             "Subcontractor shall bear the cost of the Architect's or Engineer's review of any submittal beyond the "
             "second submission of the same item."
     },
    {"id": "univ.incl.coordination_drawings", "division": None, "category": "Scope",
     "title": "Coordination Drawings", "default": True, "position": 120,
     "body": "Participation in the Project coordination and BIM process, including furnishing trade models in the "
             "required format, attending coordination sessions, resolving clashes affecting this trade, and signing "
             "off on the coordinated composite model prior to fabrication."
     },
    {"id": "univ.incl.layout", "division": None, "category": "Scope",
     "title": "Layout", "default": True, "position": 130,
     "body": "Field layout of the Subcontractor's own Work from the primary control lines and benchmarks established "
             "and maintained by the Contractor."
     },
    {"id": "univ.incl.embeds_sleeves", "division": None, "category": "Scope",
     "title": "Embeds Sleeves", "default": True, "position": 140,
     "body": "Furnishing, laying out and setting all sleeves, inserts, anchors, embeds, blockouts, hangers and "
             "supports required for this trade's Work, coordinated with and installed in time to meet the Project "
             "schedule."
     },
    {"id": "univ.incl.cutting_patching", "division": None, "category": "Scope",
     "title": "Cutting Patching", "default": True, "position": 150,
     "body": "All cutting, coring, drilling and patching required for this trade's Work, including repair of any "
             "adjacent finished work damaged by the Subcontractor's operations, restored to match existing adjacent "
             "surfaces."
     },
    {"id": "univ.incl.firestopping_own", "division": None, "category": "Scope",
     "title": "Firestopping Own", "default": True, "position": 160,
     "body": "Firestopping and smoke sealing of all penetrations created by this trade through rated assemblies, using "
             "tested and listed UL systems appropriate to the assembly and penetrant."
     },
    {"id": "univ.incl.protection", "division": None, "category": "Scope",
     "title": "Protection", "default": True, "position": 170,
     "body": "Protection of the Subcontractor's own Work and of adjacent existing and in-place Work from damage, "
             "weather, theft and the operations of other trades, until Substantial Completion."
     },
    {"id": "univ.incl.cleanup", "division": None, "category": "Scope",
     "title": "Cleanup", "default": True, "position": 180,
     "body": "Daily cleanup and removal of debris generated by this trade to the Contractor-designated containers, "
             "including broom-clean condition of work areas at the end of each shift. Composite cleanup crews will be "
             "back-charged proportionally where a trade fails to maintain its areas."
     },
    {"id": "univ.incl.waste_management", "division": None, "category": "Scope",
     "title": "Waste Management", "default": True, "position": 190,
     "body": "Compliance with the Project Construction Waste Management Plan, including source separation, use of "
             "designated recycling containers, and submission of weight tickets and diversion documentation."
     },
    {"id": "univ.incl.safety_program", "division": None, "category": "Scope",
     "title": "Safety Program", "default": True, "position": 200,
     "body": "A written site-specific safety program, job hazard analyses for each activity, designated competent "
             "persons, 100% fall protection above six feet, daily pre-task planning, and full compliance with OSHA, "
             "the authority having jurisdiction and the Contractor's safety program, whichever is most stringent."
     },
    {"id": "univ.incl.testing_inspections", "division": None, "category": "Scope",
     "title": "Testing Inspections", "default": True, "position": 210,
     "body": "All testing, start-up and inspections required of this trade by the Contract Documents or the authority "
             "having jurisdiction, including the cost of retesting and re-inspection resulting from the "
             "Subcontractor's failed or incomplete work."
     },
    {"id": "univ.incl.schedule_compliance", "division": None, "category": "Scope",
     "title": "Schedule Compliance", "default": True, "position": 220,
     "body": "Performance of the Work in accordance with the Project schedule, including furnishing manpower loading "
             "projections, participating in pull planning, and providing a written recovery plan and the additional "
             "manpower or shifts necessary to recover any delay attributable to the Subcontractor, at no additional "
             "cost."
     },
    {"id": "univ.incl.asbuilts", "division": None, "category": "Scope",
     "title": "Asbuilts", "default": True, "position": 230,
     "body": "Maintenance of a clean, current set of as-built record documents on site, updated weekly, and delivery "
             "of final record documents in the format required by the Contract Documents as a condition of final "
             "payment."
     },
    {"id": "univ.incl.om_warranties", "division": None, "category": "Scope",
     "title": "Om Warranties", "default": True, "position": 240,
     "body": "Operation and maintenance manuals, warranty documentation, spare parts and attic stock, and Owner "
             "training sessions as required by the Contract Documents."
     },
    {"id": "univ.incl.commissioning", "division": None, "category": "Scope",
     "title": "Commissioning", "default": True, "position": 250,
     "body": "Participation in the Project commissioning process, including completion of pre-functional checklists, "
             "support of functional performance testing, correction of deficiencies identified by the Commissioning "
             "Authority, and attendance at commissioning meetings."
     },
    {"id": "univ.incl.warranty", "division": None, "category": "Scope",
     "title": "Warranty", "default": True, "position": 260,
     "body": "A full parts-and-labor warranty against defects in materials and workmanship for a period of one (1) "
             "year from the date of Substantial Completion, or for the longer period specified in the Contract "
             "Documents, including any extended manufacturer warranties."
     },
    {"id": "univ.incl.punchlist", "division": None, "category": "Scope",
     "title": "Punchlist", "default": True, "position": 270,
     "body": "Completion of all punch list items within fourteen (14) calendar days of receipt of the list, and return "
             "to the site as required to complete seasonal, deferred or corrective work."
     },
    {"id": "univ.incl.temp_protection", "division": None, "category": "Scope",
     "title": "Temp Protection", "default": False, "position": 280,
     "body": "Temporary weather protection, enclosures and temporary heat required to protect this trade's Work and to "
             "maintain manufacturer-required installation conditions."
     },
    {"id": "univ.incl.hoisting_own", "division": None, "category": "Scope",
     "title": "Hoisting Own", "default": False, "position": 290,
     "body": "All hoisting, rigging, cranes, forklifts and material handling required for this trade's materials "
             "beyond the shared tower crane time allocated by the Contractor."
     },
    {"id": "univ.incl.sds", "division": None, "category": "Scope",
     "title": "Sds", "default": False, "position": 300,
     "body": "Safety Data Sheets for every product brought on site, submitted before delivery, and compliance with the "
             "Project hazard communication program."
     },
    {"id": "univ.incl.leed", "division": None, "category": "Scope",
     "title": "Leed", "default": False, "position": 310,
     "body": "All sustainability and green building documentation required for the Project's certification, including "
             "product data for recycled content, regional materials, VOC content and environmental product "
             "declarations."
     },
    {"id": "univ.incl.prevailing_wage", "division": None, "category": "Scope",
     "title": "Prevailing Wage", "default": False, "position": 320,
     "body": "Payment of prevailing wages and submission of certified payroll reports in the form and frequency "
             "required by the funding source and the authority having jurisdiction."
     },
    {"id": "univ.incl.mock_up", "division": None, "category": "Scope",
     "title": "Mock Up", "default": False, "position": 330,
     "body": "Construction of full-scale mock-ups as required by the Contract Documents, including rework until "
             "accepted by the Architect, and removal of the mock-up when directed."
     },
    {"id": "univ.excl.bonds", "division": None, "category": "Exclusions",
     "title": "Bonds", "default": True, "position": 400,
     "body": "Payment and Performance Bond. If a bond is required, it will be added by Change Order at the documented "
             "bond rate, subject to the Subcontractor's enrollment in the Contractor's Subcontractor Default Insurance "
             "program where approved."
     },
    {"id": "univ.excl.builders_risk", "division": None, "category": "Exclusions",
     "title": "Builders Risk", "default": True, "position": 410,
     "body": "Builder's Risk insurance and any deductible thereunder, which is carried by the Owner or Contractor."
     },
    {"id": "univ.excl.building_permit", "division": None, "category": "Exclusions",
     "title": "Building Permit", "default": True, "position": 420,
     "body": "The general building permit and Owner-paid impact, tap, connection and utility company fees. Trade- "
             "specific permits and licenses remain the Subcontractor's responsibility."
     },
    {"id": "univ.excl.hazmat", "division": None, "category": "Exclusions",
     "title": "Hazmat", "default": True, "position": 430,
     "body": "Identification, testing, handling, abatement or disposal of asbestos, lead, PCBs, contaminated soil, "
             "mold or any other pre-existing hazardous material not introduced by the Subcontractor."
     },
    {"id": "univ.excl.temp_utilities", "division": None, "category": "Exclusions",
     "title": "Temp Utilities", "default": True, "position": 440,
     "body": "Temporary power distribution, temporary lighting, temporary water and temporary toilets, which are "
             "furnished by the Contractor. Consumption of temporary utilities by the Subcontractor's own tools is "
             "included."
     },
    {"id": "univ.excl.overtime", "division": None, "category": "Exclusions",
     "title": "Overtime", "default": True, "position": 450,
     "body": "Overtime, shift work and premium time, except where required to recover a delay caused by the "
             "Subcontractor. Contractor-directed acceleration will be compensated by Change Order."
     },
    {"id": "univ.excl.owner_testing", "division": None, "category": "Exclusions",
     "title": "Owner Testing", "default": True, "position": 460,
     "body": "Independent third-party special inspections and quality-assurance testing engaged by the Owner. Costs of "
             "re-inspection caused by the Subcontractor's failed work are not excluded."
     },
    {"id": "univ.excl.final_cleaning", "division": None, "category": "Exclusions",
     "title": "Final Cleaning", "default": True, "position": 470,
     "body": "Final cleaning of the building prior to Owner occupancy, which is performed by the Contractor. Daily "
             "cleanup and cleaning of this trade's own installed work remain included."
     },
    {"id": "univ.excl.unknown_conditions", "division": None, "category": "Exclusions",
     "title": "Unknown Conditions", "default": True, "position": 480,
     "body": "Removal, relocation or protection of undocumented existing utilities, structures or obstructions not "
             "shown on the Contract Documents and not reasonably discoverable by a pre-bid site visit."
     },
    {"id": "univ.excl.design", "division": None, "category": "Exclusions",
     "title": "Design", "default": False, "position": 490,
     "body": "Architectural and engineering design services, except for the delegated design expressly assigned to "
             "this trade by the Contract Documents."
     },
    {"id": "univ.excl.escalation", "division": None, "category": "Exclusions",
     "title": "Escalation", "default": False, "position": 500,
     "body": "Material escalation beyond the bid validity period stated in this Exhibit, and any tariff, duty or "
             "surcharge imposed after the bid date."
     },
    {"id": "univ.excl.winter_conditions", "division": None, "category": "Exclusions",
     "title": "Winter Conditions", "default": False, "position": 510,
     "body": "Winter conditions, snow and ice removal, ground thawing and temporary heat for the building as a whole."
     },
    {"id": "univ.excl.dewatering", "division": None, "category": "Exclusions",
     "title": "Dewatering", "default": False, "position": 520,
     "body": "Site dewatering, well points and management of groundwater beyond pumping incidental to this trade's own "
             "excavations."
     },
    {"id": "univ.excl.traffic_control", "division": None, "category": "Exclusions",
     "title": "Traffic Control", "default": False, "position": 530,
     "body": "Traffic control plans, flagging, police details and street closure permits, except as expressly required "
             "for this trade's own deliveries."
     },
    {"id": "univ.excl.security", "division": None, "category": "Exclusions",
     "title": "Security", "default": False, "position": 540,
     "body": "Off-hours site security, fencing and surveillance of the Project as a whole."
     },
    {"id": "univ.excl.sales_tax", "division": None, "category": "Exclusions",
     "title": "Sales Tax", "default": False, "position": 550,
     "body": "Sales and use tax, where the Owner furnishes a valid tax exemption certificate for the Project."
     },
    {"id": "univ.excl.owner_furnished", "division": None, "category": "Exclusions",
     "title": "Owner Furnished", "default": False, "position": 560,
     "body": "Receiving, storage, handling and installation of Owner-furnished equipment, except where expressly "
             "listed as included in this Exhibit."
     },
    {"id": "univ.excl.impact_costs", "division": None, "category": "Exclusions",
     "title": "Impact Costs", "default": False, "position": 570,
     "body": "Costs arising from impact, acceleration, out-of-sequence work or inefficiency caused by others, which "
             "will be addressed under the Contract's change provisions."
     },
    {"id": "univ.clar.documents_basis", "division": None, "category": "Clarifications",
     "title": "Documents Basis", "default": True, "position": 600,
     "body": "This Scope of Work is based on the Drawings and Specifications identified in the Contract Documents, "
             "including all addenda issued through the bid date. Subsequent revisions will be handled as changes to "
             "the Work."
     },
    {"id": "univ.clar.precedence", "division": None, "category": "Clarifications",
     "title": "Precedence", "default": True, "position": 610,
     "body": "In the event of a conflict between this Exhibit and the Contract Documents, the Contract Documents "
             "govern and the more stringent requirement applies. Nothing listed as an exclusion overrides work "
             "expressly required of this trade by the Contract Documents."
     },
    {"id": "univ.clar.normal_hours", "division": None, "category": "Clarifications",
     "title": "Normal Hours", "default": True, "position": 620,
     "body": "Pricing assumes performance of the Work during normal working hours, Monday through Friday, in a "
             "continuous and uninterrupted sequence, with reasonable and unobstructed access to the work areas."
     },
    {"id": "univ.clar.bid_validity", "division": None, "category": "Clarifications",
     "title": "Bid Validity", "default": False, "position": 630,
     "body": "This proposal is valid for thirty (30) days from the date of submission unless extended in writing."
     },
    {"id": "univ.clar.single_mobilization", "division": None, "category": "Clarifications",
     "title": "Single Mobilization", "default": False, "position": 640,
     "body": "Pricing assumes a single mobilization and demobilization per work area. Additional mobilizations "
             "requested by the Contractor will be compensated at the unit prices stated in this Exhibit."
     },
    {"id": "univ.clar.staging", "division": None, "category": "Clarifications",
     "title": "Staging", "default": False, "position": 650,
     "body": "Pricing assumes the Contractor provides on-site laydown and staging area within reasonable proximity to "
             "the work face, and reasonable access for delivery vehicles."
     },
    {"id": "univ.clar.substitutions", "division": None, "category": "Clarifications",
     "title": "Substitutions", "default": False, "position": 660,
     "body": "No substitutions or value engineering options are included unless expressly listed in this Exhibit and "
             "accepted in writing by the Owner and Architect."
     },
    {"id": "univ.close.record_docs", "division": None, "category": "Closeout",
     "title": "Record Docs", "default": True, "position": 700,
     "body": "Final as-built record drawings and specifications, in both marked-up print and electronic form, "
             "delivered prior to the final application for payment."
     },
    {"id": "univ.close.om_training", "division": None, "category": "Closeout",
     "title": "Om Training", "default": True, "position": 710,
     "body": "Operation and maintenance manuals, equipment warranties, and documented Owner training sessions, "
             "recorded where required by the Contract Documents."
     },
    {"id": "univ.close.lien_waivers", "division": None, "category": "Closeout",
     "title": "Lien Waivers", "default": True, "position": 720,
     "body": "Final unconditional lien waivers from the Subcontractor and from every lower-tier subcontractor and "
             "material supplier, along with a consent of surety where a bond is in place."
     },
    {"id": "univ.close.attic_stock", "division": None, "category": "Closeout",
     "title": "Attic Stock", "default": False, "position": 730,
     "body": "Delivery of all specified spare parts, attic stock and extra materials to the Owner, with a signed "
             "transmittal."
     },
    {"id": "univ.sched.milestones", "division": None, "category": "Schedule",
     "title": "Milestones", "default": False, "position": 800,
     "body": "Subcontractor shall meet the milestone dates set out in the Project schedule and shall notify the "
             "Contractor in writing within forty-eight (48) hours of becoming aware of any condition that may affect a "
             "milestone."
     },
    {"id": "univ.sched.submittal_lead", "division": None, "category": "Schedule",
     "title": "Submittal Lead", "default": False, "position": 810,
     "body": "Initial submittals shall be delivered within twenty-one (21) calendar days of the notice to proceed, and "
             "long-lead material shall be released for fabrication immediately upon submittal approval."
     },
    {"id": "univ.safety.competent_person", "division": None, "category": "Safety",
     "title": "Competent Person", "default": False, "position": 900,
     "body": "A designated competent person shall be on site whenever this trade is working, for each activity "
             "requiring one under OSHA, including excavation, scaffolding, fall protection, rigging and confined space "
             "entry."
     },
    {"id": "univ.safety.hot_work", "division": None, "category": "Safety",
     "title": "Hot Work", "default": False, "position": 910,
     "body": "All hot work requires a permit issued by the Contractor, a dedicated fire watch during the work and for "
             "thirty (30) minutes afterward, and appropriate fire extinguishing equipment at the work location."
     },
    {"id": "univ.safety.loto", "division": None, "category": "Safety",
     "title": "Loto", "default": False, "position": 920,
     "body": "Compliance with the Project lockout/tagout and energized work programs, including written energized work "
             "permits where de-energizing is not feasible."
     },
    {"id": "d02.incl.selective_demo", "division": "02", "category": "Scope",
     "title": "Selective Demo", "default": True, "position": 10,
     "body": "Complete selective demolition of the structures, finishes, systems and site elements indicated for "
             "removal, including all shoring, bracing and temporary support required to maintain the stability of "
             "remaining construction."
     },
    {"id": "d02.incl.salvage", "division": "02", "category": "Scope",
     "title": "Salvage", "default": True, "position": 20,
     "body": "Careful removal, protection, tagging and turnover to the Owner of all items identified for salvage, and "
             "disposal of all other demolished material at a properly licensed facility."
     },
    {"id": "d02.incl.dust_control", "division": "02", "category": "Scope",
     "title": "Dust Control", "default": True, "position": 30,
     "body": "Temporary dust partitions, negative air machines, HEPA filtration, floor protection and noise mitigation "
             "as required to permit adjacent areas to remain occupied and operational during demolition."
     },
    {"id": "d02.incl.utility_disconnect", "division": "02", "category": "Scope",
     "title": "Utility Disconnect", "default": True, "position": 40,
     "body": "Locating, safing-off, capping and documenting all utilities serving the areas to be demolished, "
             "coordinated with the utility owner and the Contractor prior to any removal."
     },
    {"id": "d02.incl.survey", "division": "02", "category": "Scope",
     "title": "Survey", "default": True, "position": 50,
     "body": "Pre-demolition condition survey with photographic and video documentation of adjacent structures, "
             "finishes and public ways, issued to the Contractor before mobilization."
     },
    {"id": "d02.incl.recycling", "division": "02", "category": "Scope",
     "title": "Recycling", "default": False, "position": 60,
     "body": "Source separation and recycling of demolition debris to meet the Project diversion rate, with weight "
             "tickets and diversion reports submitted monthly."
     },
    {"id": "d02.excl.abatement", "division": "02", "category": "Exclusions",
     "title": "Abatement", "default": True, "position": 200,
     "body": "Abatement of asbestos-containing material, lead-based paint and other regulated hazardous materials, "
             "which is performed under a separate abatement contract."
     },
    {"id": "d02.excl.structural_design", "division": "02", "category": "Exclusions",
     "title": "Structural Design", "default": False, "position": 210,
     "body": "Engineering design of permanent structural modifications. Design of temporary shoring required for the "
             "Subcontractor's means and methods is included."
     },
    {"id": "d03.incl.cip_complete", "division": "03", "category": "Scope",
     "title": "Cip Complete", "default": True, "position": 10,
     "body": "Complete cast-in-place concrete Work, including formwork, shoring, reshoring, reinforcing steel "
             "furnishing and placement, embeds, concrete placement, consolidation, finishing, curing and protection."
     },
    {"id": "d03.incl.rebar", "division": "03", "category": "Scope",
     "title": "Rebar", "default": True, "position": 20,
     "body": "Furnishing, detailing, fabricating, delivering and installing all reinforcing steel, welded wire "
             "reinforcement, dowels, couplers, chairs, bolsters and accessories, including placing drawings and bar "
             "lists."
     },
    {"id": "d03.incl.mix_designs", "division": "03", "category": "Scope",
     "title": "Mix Designs", "default": True, "position": 30,
     "body": "Submission of concrete mix designs for each class of concrete, supported by trial batch data or "
             "historical strength records, for review prior to the first placement."
     },
    {"id": "d03.incl.slab_flatness", "division": "03", "category": "Scope",
     "title": "Slab Flatness", "default": True, "position": 40,
     "body": "Achievement of the specified floor flatness and levelness tolerances, and grinding, topping or "
             "replacement of any slab area failing to meet the specified F-numbers at no additional cost."
     },
    {"id": "d03.incl.embeds_coordination", "division": "03", "category": "Scope",
     "title": "Embeds Coordination", "default": True, "position": 50,
     "body": "Installation of all embeds, anchor bolts, sleeves, blockouts and inserts furnished by other trades, "
             "based on templates and layout information supplied by those trades in advance of placement."
     },
    {"id": "d03.incl.joints", "division": "03", "category": "Scope",
     "title": "Joints", "default": True, "position": 60,
     "body": "Construction, control and expansion joints located per approved joint layout drawings, including "
             "sawcutting within the required time window, joint filler and sealant."
     },
    {"id": "d03.incl.curing_protection", "division": "03", "category": "Scope",
     "title": "Curing Protection", "default": True, "position": 70,
     "body": "Curing, cold-weather and hot-weather protection measures, including blankets, enclosures, heaters, "
             "evaporation retarders and admixtures necessary to place concrete in the actual conditions encountered."
     },
    {"id": "d03.incl.surface_prep", "division": "03", "category": "Scope",
     "title": "Surface Prep", "default": False, "position": 80,
     "body": "Surface preparation of slabs to the profile and moisture condition required by the flooring "
             "manufacturer, including shot blasting or grinding and remediation of laitance and curing compound "
             "residue."
     },
    {"id": "d03.incl.moisture_testing", "division": "03", "category": "Scope",
     "title": "Moisture Testing", "default": False, "position": 90,
     "body": "Relative humidity and moisture vapor emission testing of slabs prior to flooring installation, with "
             "results reported to the Contractor."
     },
    {"id": "d03.excl.testing_agency", "division": "03", "category": "Exclusions",
     "title": "Testing Agency", "default": True, "position": 200,
     "body": "Owner's independent testing laboratory for cylinder breaks, slump and air content testing. Providing "
             "safe access and assistance to the testing agency is included."
     },
    {"id": "d03.excl.subgrade", "division": "03", "category": "Exclusions",
     "title": "Subgrade", "default": True, "position": 210,
     "body": "Preparation, proof-rolling and compaction of subgrade, and furnishing of granular base beneath slabs on "
             "grade, which is by the Earthwork Subcontractor."
     },
    {"id": "d03.excl.vapor_barrier", "division": "03", "category": "Exclusions",
     "title": "Vapor Barrier", "default": False, "position": 220,
     "body": "Under-slab vapor retarder and its taping and sealing at penetrations, unless expressly included in this "
             "Exhibit."
     },
    {"id": "d03.excl.structural_steel", "division": "03", "category": "Exclusions",
     "title": "Structural Steel", "default": False, "position": 230,
     "body": "Furnishing of structural steel embeds, bearing plates and anchor rod assemblies, which are furnished by "
             "the Structural Steel Subcontractor for installation under this Subcontract."
     },
    {"id": "d04.incl.unit_masonry", "division": "04", "category": "Scope",
     "title": "Unit Masonry", "default": True, "position": 10,
     "body": "Complete unit masonry Work including concrete masonry units, face brick, mortar, grout, reinforcing, "
             "ties, anchors, lintels installation, flashing installation and accessories."
     },
    {"id": "d04.incl.scaffolding", "division": "04", "category": "Scope",
     "title": "Scaffolding", "default": True, "position": 20,
     "body": "All scaffolding, mast climbers, hoists and material handling required for the masonry Work, including "
             "engineering, erection, inspection, maintenance and removal."
     },
    {"id": "d04.incl.cleaning", "division": "04", "category": "Scope",
     "title": "Cleaning", "default": True, "position": 30,
     "body": "Final cleaning of all exposed masonry surfaces using methods approved by the masonry manufacturer, "
             "including removal of mortar smears and efflorescence."
     },
    {"id": "d04.incl.cold_weather", "division": "04", "category": "Scope",
     "title": "Cold Weather", "default": True, "position": 40,
     "body": "Cold-weather and hot-weather masonry construction procedures per the governing masonry code, including "
             "enclosures, heated enclosures, admixtures and protection of newly laid masonry."
     },
    {"id": "d04.incl.mockup", "division": "04", "category": "Scope",
     "title": "Mockup", "default": True, "position": 50,
     "body": "Construction and maintenance of the sample masonry panel for each exposed masonry type, including rework "
             "until accepted, and retention on site as the quality standard for the Work."
     },
    {"id": "d04.incl.flashing_install", "division": "04", "category": "Scope",
     "title": "Flashing Install", "default": False, "position": 60,
     "body": "Installation of through-wall flashing, end dams, weeps and drainage mat within the masonry cavity, "
             "coordinated with the roofing and waterproofing trades."
     },
    {"id": "d04.excl.lintels_furnish", "division": "04", "category": "Exclusions",
     "title": "Lintels Furnish", "default": True, "position": 200,
     "body": "Furnishing of loose steel lintels, shelf angles and relieving angles, which are furnished by the Metals "
             "Subcontractor for installation under this Subcontract."
     },
    {"id": "d04.excl.air_barrier", "division": "04", "category": "Exclusions",
     "title": "Air Barrier", "default": False, "position": 210,
     "body": "Air barrier and fluid-applied waterproofing on the backup wall, which is by the Division 07 "
             "Subcontractor."
     },
    {"id": "d05.incl.structural_steel", "division": "05", "category": "Scope",
     "title": "Structural Steel", "default": True, "position": 10,
     "body": "Complete structural steel package including detailing, fabrication, shop priming, delivery, field "
             "erection, bolting, welding and final connections of all structural steel, joists, joist girders and "
             "metal deck."
     },
    {"id": "d05.incl.connection_design", "division": "05", "category": "Scope",
     "title": "Connection Design", "default": True, "position": 20,
     "body": "Delegated design of all steel connections by a professional engineer licensed in the Project "
             "jurisdiction, with sealed calculations and connection details submitted for review."
     },
    {"id": "d05.incl.erection_engineering", "division": "05", "category": "Scope",
     "title": "Erection Engineering", "default": True, "position": 30,
     "body": "Erection engineering, temporary bracing, guying and stability of the structure until all permanent "
             "connections, decking and diaphragms are complete, designed by a licensed professional engineer."
     },
    {"id": "d05.incl.misc_metals", "division": "05", "category": "Scope",
     "title": "Misc Metals", "default": True, "position": 40,
     "body": "Miscellaneous and ornamental metals including stairs, landings, handrails, guardrails, ladders, "
             "bollards, lintels, shelf angles, embeds, bumper posts and support framing not furnished under another "
             "Section."
     },
    {"id": "d05.incl.welding_qc", "division": "05", "category": "Scope",
     "title": "Welding Qc", "default": True, "position": 50,
     "body": "Certified welding procedures, welder qualification records, and the Subcontractor's own quality control "
             "inspection of shop and field welds."
     },
    {"id": "d05.incl.touch_up", "division": "05", "category": "Scope",
     "title": "Touch Up", "default": True, "position": 60,
     "body": "Field touch-up of shop primer at all connections, abrasions, burn marks and areas damaged during "
             "shipping and erection."
     },
    {"id": "d05.incl.deck_closure", "division": "05", "category": "Scope",
     "title": "Deck Closure", "default": False, "position": 70,
     "body": "Metal deck closure pieces, pour stops, edge angles, sump pans and deck reinforcement at openings up to "
             "the size indicated on the structural drawings."
     },
    {"id": "d05.excl.special_inspection", "division": "05", "category": "Exclusions",
     "title": "Special Inspection", "default": True, "position": 200,
     "body": "Owner's special inspection of high-strength bolting and field welding. Correction of deficiencies "
             "identified by the special inspector and the cost of re-inspection are included."
     },
    {"id": "d05.excl.fireproofing", "division": "05", "category": "Exclusions",
     "title": "Fireproofing", "default": True, "position": 210,
     "body": "Spray-applied fireproofing and intumescent coatings, which are by the Division 07 Subcontractor."
     },
    {"id": "d05.excl.anchor_bolt_install", "division": "05", "category": "Exclusions",
     "title": "Anchor Bolt Install", "default": False, "position": 220,
     "body": "Setting of anchor rods and leveling plates into concrete, which is performed by the Concrete "
             "Subcontractor from templates furnished under this Subcontract."
     },
    {"id": "d06.incl.rough_carpentry", "division": "06", "category": "Scope",
     "title": "Rough Carpentry", "default": True, "position": 10,
     "body": "All rough carpentry including wood blocking, nailers, furring, curbs, sleepers, plates and backing "
             "required for the attachment of work by all trades, whether or not specifically indicated on the "
             "drawings."
     },
    {"id": "d06.incl.millwork", "division": "06", "category": "Scope",
     "title": "Millwork", "default": True, "position": 20,
     "body": "Shop drawings, fabrication, finishing, delivery and installation of all architectural millwork and "
             "casework to the grade specified, including hardware, filler panels, scribes and closure pieces."
     },
    {"id": "d06.incl.field_measure", "division": "06", "category": "Scope",
     "title": "Field Measure", "default": True, "position": 30,
     "body": "Field verification of all dimensions prior to fabrication. The Subcontractor accepts responsibility for "
             "fit and shall bear the cost of rework arising from failure to field measure."
     },
    {"id": "d06.incl.fire_treated", "division": "06", "category": "Scope",
     "title": "Fire Treated", "default": True, "position": 40,
     "body": "Fire-retardant-treated and preservative-treated lumber where required by code or the Contract Documents, "
             "with treatment certifications submitted."
     },
    {"id": "d06.incl.acclimation", "division": "06", "category": "Scope",
     "title": "Acclimation", "default": False, "position": 50,
     "body": "Delivery of millwork only after the building is enclosed and permanent HVAC is operating, with "
             "acclimation of materials for the period required by the manufacturer."
     },
    {"id": "d06.excl.countertops", "division": "06", "category": "Exclusions",
     "title": "Countertops", "default": False, "position": 200,
     "body": "Solid surface, quartz and stone countertops, unless expressly listed as included in this Exhibit."
     },
    {"id": "d06.excl.appliances", "division": "06", "category": "Exclusions",
     "title": "Appliances", "default": False, "position": 210,
     "body": "Furnishing of appliances and equipment set into casework. Cutouts and coordination for their "
             "installation are included."
     },
    {"id": "d07.incl.roofing_system", "division": "07", "category": "Scope",
     "title": "Roofing System", "default": True, "position": 10,
     "body": "Complete roofing system including vapor retarder, insulation, tapered insulation to achieve positive "
             "drainage, cover board, membrane, flashings, edge metal, walkway pads and all accessories required for a "
             "warrantable installation."
     },
    {"id": "d07.incl.warranty_ndl", "division": "07", "category": "Scope",
     "title": "Warranty Ndl", "default": True, "position": 20,
     "body": "Manufacturer's no-dollar-limit total system warranty for the specified term, with the Subcontractor's "
             "own two-year labor and workmanship warranty, and all manufacturer field inspections required to secure "
             "it."
     },
    {"id": "d07.incl.temporary_roof", "division": "07", "category": "Scope",
     "title": "Temporary Roof", "default": True, "position": 30,
     "body": "Temporary roofing, night seals and water cut-offs at the end of each work day sufficient to keep the "
             "building watertight, and removal of the same as permanent work proceeds."
     },
    {"id": "d07.incl.waterproofing", "division": "07", "category": "Scope",
     "title": "Waterproofing", "default": True, "position": 40,
     "body": "Below-grade and horizontal waterproofing, air and vapor barriers, dampproofing, protection board, "
             "drainage composite and all transitions and terminations to adjacent assemblies."
     },
    {"id": "d07.incl.firestopping_system", "division": "07", "category": "Scope",
     "title": "Firestopping System", "default": True, "position": 50,
     "body": "Through-penetration and joint firestopping for all rated assemblies, including tested UL system "
             "selection, submittal of a firestop schedule, installation and identification labeling at each location."
     },
    {"id": "d07.incl.sealants", "division": "07", "category": "Scope",
     "title": "Sealants", "default": True, "position": 60,
     "body": "Exterior joint sealants at all building envelope joints, including backer rod, primer, adhesion testing "
             "and a sealant warranty for the specified term."
     },
    {"id": "d07.incl.fireproofing", "division": "07", "category": "Scope",
     "title": "Fireproofing", "default": False, "position": 70,
     "body": "Spray-applied fire-resistive material and intumescent coatings to the thicknesses required by the "
             "approved UL designs, including patching after other trades and thickness/density testing."
     },
    {"id": "d07.incl.leak_testing", "division": "07", "category": "Scope",
     "title": "Leak Testing", "default": False, "position": 80,
     "body": "Flood testing of horizontal waterproofing and water testing of envelope mock-ups per the Contract "
             "Documents, including repair and retesting until passing."
     },
    {"id": "d07.excl.roof_structure", "division": "07", "category": "Exclusions",
     "title": "Roof Structure", "default": True, "position": 200,
     "body": "Roof deck, structural framing, and wood blocking and nailers, which are by others. Coordination of "
             "blocking locations is included."
     },
    {"id": "d07.excl.roof_penetrations", "division": "07", "category": "Exclusions",
     "title": "Roof Penetrations", "default": False, "position": 210,
     "body": "Furnishing of mechanical curbs, equipment supports and pipe penetration sleeves, which are furnished by "
             "the respective trades. Flashing them into the roof system is included."
     },
    {"id": "d08.incl.doors_frames_hardware", "division": "08", "category": "Scope",
     "title": "Doors Frames Hardware", "default": True, "position": 10,
     "body": "Furnishing and installing all hollow metal frames, doors, wood doors and finish hardware, complete with "
             "a hardware schedule prepared and signed by a certified Architectural Hardware Consultant."
     },
    {"id": "d08.incl.glazing", "division": "08", "category": "Scope",
     "title": "Glazing", "default": True, "position": 20,
     "body": "Complete aluminum entrance, storefront and curtain wall systems, including glass, glazing, gaskets, "
             "perimeter sealants, anchors, flashing, sill pans and all associated trim."
     },
    {"id": "d08.incl.delegated_design", "division": "08", "category": "Scope",
     "title": "Delegated Design", "default": True, "position": 30,
     "body": "Delegated design of curtain wall and storefront systems for the specified wind, seismic, thermal "
             "movement and deflection criteria, sealed by a professional engineer licensed in the Project "
             "jurisdiction."
     },
    {"id": "d08.incl.hardware_coordination", "division": "08", "category": "Scope",
     "title": "Hardware Coordination", "default": True, "position": 40,
     "body": "Coordination of all electrified hardware, including furnishing point-to-point wiring diagrams, power and "
             "low-voltage requirements, and attendance at door hardware coordination meetings with the electrical and "
             "security trades."
     },
    {"id": "d08.incl.keying", "division": "08", "category": "Scope",
     "title": "Keying", "default": True, "position": 50,
     "body": "Keying conference with the Owner, preparation of the keying schedule, furnishing of permanent cylinders "
             "and keys, and a construction keying system removed at turnover."
     },
    {"id": "d08.incl.overhead_doors", "division": "08", "category": "Scope",
     "title": "Overhead Doors", "default": False, "position": 60,
     "body": "Overhead coiling doors, sectional doors, grilles and operators, including motor operators, safety "
             "devices and final adjustment."
     },
    {"id": "d08.excl.electrified_power", "division": "08", "category": "Exclusions",
     "title": "Electrified Power", "default": True, "position": 200,
     "body": "Line-voltage power to door hardware, access control head-end equipment and low-voltage cabling, which "
             "are by the Electrical and Security Subcontractors."
     },
    {"id": "d08.excl.blocking", "division": "08", "category": "Exclusions",
     "title": "Blocking", "default": False, "position": 210,
     "body": "Wall blocking, backing and rough openings, which are furnished and installed by others in accordance "
             "with dimensions provided under this Subcontract."
     },
    {"id": "d09.incl.framing_drywall", "division": "09", "category": "Scope",
     "title": "Framing Drywall", "default": True, "position": 10,
     "body": "Complete non-structural metal framing and gypsum board assemblies, including deflection track, bracing, "
             "backing, insulation within partitions, corner bead, trim, joint treatment to the specified level of "
             "finish, and rated assembly construction per the approved UL designs."
     },
    {"id": "d09.incl.acoustical", "division": "09", "category": "Scope",
     "title": "Acoustical", "default": True, "position": 20,
     "body": "Acoustical ceiling systems including suspension grid, hanger wire, seismic bracing and restraint per the "
             "governing code, tile, perimeter trim and coordination of all ceiling-mounted devices."
     },
    {"id": "d09.incl.flooring", "division": "09", "category": "Scope",
     "title": "Flooring", "default": True, "position": 30,
     "body": "All flooring Work including substrate preparation, self-leveling underlayment, moisture mitigation where "
             "required by test results, adhesives, base, transitions and protection until turnover."
     },
    {"id": "d09.incl.painting", "division": "09", "category": "Scope",
     "title": "Painting", "default": True, "position": 40,
     "body": "All painting and coating including surface preparation, priming, the specified number of finish coats, "
             "painting of exposed conduit, piping, ductwork and equipment where scheduled, and touch-up at punch list."
     },
    {"id": "d09.incl.tile", "division": "09", "category": "Scope",
     "title": "Tile", "default": False, "position": 50,
     "body": "Ceramic and porcelain tile including setting materials, waterproof membrane, crack isolation membrane, "
             "movement joints, grout, sealing and transition profiles."
     },
    {"id": "d09.incl.rated_assemblies", "division": "09", "category": "Scope",
     "title": "Rated Assemblies", "default": True, "position": 60,
     "body": "Construction of fire-rated and smoke-rated partitions in strict accordance with the approved UL designs, "
             "including head-of-wall joint systems, correct fastener patterns and rated assembly identification "
             "stenciling above ceilings."
     },
    {"id": "d09.incl.attic_stock_finishes", "division": "09", "category": "Scope",
     "title": "Attic Stock Finishes", "default": False, "position": 70,
     "body": "Attic stock of each flooring, tile, ceiling tile and paint color in the quantities specified, delivered "
             "and turned over to the Owner."
     },
    {"id": "d09.excl.substrate_defects", "division": "09", "category": "Exclusions",
     "title": "Substrate Defects", "default": False, "position": 200,
     "body": "Correction of substrate defects exceeding the tolerances of the applicable industry standard, including "
             "grinding or filling of slabs outside the specified F-number tolerances."
     },
    {"id": "d09.excl.moisture_mitigation", "division": "09", "category": "Exclusions",
     "title": "Moisture Mitigation", "default": False, "position": 210,
     "body": "Moisture vapor mitigation systems where slab moisture exceeds the flooring manufacturer's limits, which "
             "will be added by Change Order based on documented test results."
     },
    {"id": "d10.incl.specialties", "division": "10", "category": "Scope",
     "title": "Specialties", "default": True, "position": 10,
     "body": "Furnishing and installing all specialty items scheduled, including toilet partitions, toilet and bath "
             "accessories, corner guards, lockers, fire extinguishers and cabinets, signage and visual display units, "
             "complete with all anchors and mounting hardware."
     },
    {"id": "d10.incl.signage_permits", "division": "10", "category": "Scope",
     "title": "Signage Permits", "default": False, "position": 20,
     "body": "Code-required signage including room identification, egress, and ADA-compliant tactile and Braille "
             "signage, with a submitted sign message schedule for Owner approval."
     },
    {"id": "d10.excl.blocking_specialties", "division": "10", "category": "Exclusions",
     "title": "Blocking Specialties", "default": True, "position": 200,
     "body": "In-wall blocking and backing, which is installed by others in accordance with mounting height and "
             "location information furnished under this Subcontract."
     },
    {"id": "d11.incl.equipment", "division": "11", "category": "Scope",
     "title": "Equipment", "default": True, "position": 10,
     "body": "Furnishing, delivery, setting, anchoring and final connection of all specified equipment, including "
             "manufacturer start-up, testing and Owner training."
     },
    {"id": "d11.excl.rough_ins", "division": "11", "category": "Exclusions",
     "title": "Rough Ins", "default": True, "position": 200,
     "body": "Mechanical, plumbing and electrical rough-in to within five feet of the equipment, which is by the "
             "respective trades from rough-in drawings furnished under this Subcontract."
     },
    {"id": "d14.incl.elevators", "division": "14", "category": "Scope",
     "title": "Elevators", "default": True, "position": 10,
     "body": "Complete elevator systems including machines, controllers, rails, cabs, doors, fixtures, wiring within "
             "the hoistway and machine room, testing, inspection by the authority having jurisdiction, and all permits "
             "and licenses for the elevator installation."
     },
    {"id": "d14.incl.temp_use", "division": "14", "category": "Scope",
     "title": "Temp Use", "default": False, "position": 20,
     "body": "Temporary use of one elevator for construction purposes, including protective padding, operator where "
             "required, and refurbishment to new condition prior to turnover."
     },
    {"id": "d14.excl.hoistway_work", "division": "14", "category": "Exclusions",
     "title": "Hoistway Work", "default": True, "position": 200,
     "body": "Hoistway construction, pit waterproofing, sump, machine room HVAC, standby power, shunt trip, fire alarm "
             "interface and hoistway lighting, which are by others."
     },
    {"id": "d21.incl.design", "division": "21", "category": "Scope",
     "title": "Design", "default": True, "position": 10,
     "body": "Complete hydraulically calculated design of the wet and dry sprinkler systems by a NICET Level III or "
             "higher designer or a licensed fire protection engineer, including full submittal to the Architect, "
             "Engineer, the authority having jurisdiction and the Owner's insurance carrier for approval, and revision "
             "until approved."
     },
    {"id": "d21.incl.systems", "division": "21", "category": "Scope",
     "title": "Systems", "default": True, "position": 20,
     "body": "Furnishing and installing complete wet, dry, pre-action and standpipe systems, including piping, "
             "hangers, seismic bracing, sprinkler heads, escutcheons, valves, tamper and flow switches, inspector test "
             "connections, drains and auxiliary drains."
     },
    {"id": "d21.incl.fdc", "division": "21", "category": "Scope",
     "title": "Fdc", "default": True, "position": 30,
     "body": "All fire department connections, drain lines and inspector test line locations, coordinated with the "
             "Owner, Architect, the authority having jurisdiction and the Owner's insurance carrier, and terminated to "
             "approved points of discharge."
     },
    {"id": "d21.incl.fire_pump", "division": "21", "category": "Scope",
     "title": "Fire Pump", "default": True, "position": 40,
     "body": "Fire pump, jockey pump, fire pump controller, suction and discharge piping, test header, flow meter, and "
             "all pump accessories, including factory certified acceptance testing."
     },
    {"id": "d21.incl.heat_trace", "division": "21", "category": "Scope",
     "title": "Heat Trace", "default": False, "position": 50,
     "body": "Insulation and heat tracing of wet system piping routed through unheated space, including parking decks, "
             "attics and loading docks, complete with thermostats and end-seal kits."
     },
    {"id": "d21.incl.temp_standpipes", "division": "21", "category": "Scope",
     "title": "Temp Standpipes", "default": True, "position": 60,
     "body": "Temporary standpipes maintained in service throughout construction in accordance with NFPA 241, OSHA and "
             "the requirements of the authority having jurisdiction, including relocation as the structure rises and "
             "removal at completion."
     },
    {"id": "d21.incl.seismic_bracing", "division": "21", "category": "Scope",
     "title": "Seismic Bracing", "default": True, "position": 70,
     "body": "Seismic bracing, restraints and flexible couplings for all fire suppression piping per NFPA 13 and the "
             "governing building code, with sealed calculations where required."
     },
    {"id": "d21.incl.testing_acceptance", "division": "21", "category": "Scope",
     "title": "Testing Acceptance", "default": True, "position": 80,
     "body": "Hydrostatic testing, flushing, main drain tests, and the complete NFPA contractor's material and test "
             "certificates for above-ground and underground piping, witnessed by the authority having jurisdiction."
     },
    {"id": "d21.incl.coordination_ceiling", "division": "21", "category": "Scope",
     "title": "Coordination Ceiling", "default": True, "position": 90,
     "body": "Coordination of sprinkler head locations with the reflected ceiling plans, light fixtures, diffusers, "
             "structure and other trades, with center-of-tile placement in lay-in ceilings unless directed otherwise."
     },
    {"id": "d21.incl.special_hazard", "division": "21", "category": "Scope",
     "title": "Special Hazard", "default": False, "position": 100,
     "body": "Clean agent, water mist and specialty suppression systems for protected rooms, including detection, "
             "releasing panel, cylinders, nozzles, room integrity testing and discharge testing."
     },
    {"id": "d21.incl.underground", "division": "21", "category": "Scope",
     "title": "Underground", "default": False, "position": 110,
     "body": "Underground fire service main from five feet outside the building to the riser, including thrust blocks, "
             "restraints, post indicator valve, backflow preventer and flushing."
     },
    {"id": "d21.excl.fire_alarm", "division": "21", "category": "Exclusions",
     "title": "Fire Alarm", "default": True, "position": 200,
     "body": "Fire alarm system, alarm panel, initiating and notification devices, and all wiring and monitoring of "
             "tamper and flow switches, which are by the Division 28 Subcontractor. Furnishing the switches for their "
             "connection is included."
     },
    {"id": "d21.excl.power_wiring", "division": "21", "category": "Exclusions",
     "title": "Power Wiring", "default": True, "position": 210,
     "body": "Line-voltage power wiring and disconnects to the fire pump and controller, which are by the Electrical "
             "Subcontractor."
     },
    {"id": "d21.excl.rated_penetrations_others", "division": "21", "category": "Exclusions",
     "title": "Rated Penetrations Others", "default": False, "position": 220,
     "body": "Firestopping of penetrations created by other trades. Firestopping of this trade's own penetrations is "
             "included."
     },
    {"id": "d21.excl.painting_exposed", "division": "21", "category": "Exclusions",
     "title": "Painting Exposed", "default": False, "position": 230,
     "body": "Field painting of exposed sprinkler piping, which is by the Painting Subcontractor. Factory finish on "
             "specified heads and escutcheons is included."
     },
    {"id": "d22.incl.complete_systems", "division": "22", "category": "Scope",
     "title": "Complete Systems", "default": True, "position": 10,
     "body": "Complete plumbing systems including domestic hot and cold water, sanitary waste and vent, storm "
             "drainage, natural gas, and all fixtures, trim, carriers, valves, insulation, hangers and seismic "
             "restraints."
     },
    {"id": "d22.incl.underslab", "division": "22", "category": "Scope",
     "title": "Underslab", "default": True, "position": 20,
     "body": "All under-slab and below-grade plumbing rough-in including excavation, bedding, backfill and compaction "
             "within the building footprint, and inspection prior to cover."
     },
    {"id": "d22.incl.fixtures", "division": "22", "category": "Scope",
     "title": "Fixtures", "default": True, "position": 30,
     "body": "Furnishing and setting all plumbing fixtures, faucets, flush valves, carriers, stops, traps, escutcheons "
             "and accessories, complete and operating, including final connection of Owner-furnished fixtures."
     },
    {"id": "d22.incl.testing_disinfection", "division": "22", "category": "Scope",
     "title": "Testing Disinfection", "default": True, "position": 40,
     "body": "Pressure testing, disinfection and bacteriological testing of the domestic water system, with passing "
             "laboratory results submitted prior to occupancy."
     },
    {"id": "d22.incl.water_heaters", "division": "22", "category": "Scope",
     "title": "Water Heaters", "default": True, "position": 50,
     "body": "Water heaters, recirculation pumps, mixing valves, expansion tanks, backflow preventers and associated "
             "piping specialties, complete with start-up and certification of backflow devices by a licensed tester."
     },
    {"id": "d22.incl.medical_gas", "division": "22", "category": "Scope",
     "title": "Medical Gas", "default": False, "position": 60,
     "body": "Medical gas systems installed by ASSE 6010 certified installers, with brazing under nitrogen purge, and "
             "third-party verification by an ASSE 6030 verifier."
     },
    {"id": "d22.incl.grease", "division": "22", "category": "Scope",
     "title": "Grease", "default": False, "position": 70,
     "body": "Grease interceptors, sand and oil separators, trench drains and associated venting, including "
             "coordination with the authority having jurisdiction."
     },
    {"id": "d22.excl.site_utilities", "division": "22", "category": "Exclusions",
     "title": "Site Utilities", "default": True, "position": 200,
     "body": "Site utilities beyond five feet outside the building line, which are by the Site Utilities "
             "Subcontractor, including tap fees and utility company charges."
     },
    {"id": "d22.excl.electrical_connections", "division": "22", "category": "Exclusions",
     "title": "Electrical Connections", "default": True, "position": 210,
     "body": "Line-voltage power, disconnects and starters for plumbing equipment, which are by the Electrical "
             "Subcontractor. Control wiring integral to the plumbing equipment is included."
     },
    {"id": "d22.excl.kitchen_equipment", "division": "22", "category": "Exclusions",
     "title": "Kitchen Equipment", "default": False, "position": 220,
     "body": "Furnishing of food service equipment. Rough-in and final connection of that equipment per the approved "
             "kitchen equipment drawings is included."
     },
    {"id": "d23.incl.complete_hvac", "division": "23", "category": "Scope",
     "title": "Complete Hvac", "default": True, "position": 10,
     "body": "Complete HVAC systems including air handling units, rooftop units, chillers, boilers, pumps, terminal "
             "units, ductwork, piping, insulation, grilles, registers, diffusers, dampers, hangers and seismic "
             "restraints."
     },
    {"id": "d23.incl.ductwork", "division": "23", "category": "Scope",
     "title": "Ductwork", "default": True, "position": 20,
     "body": "Fabrication and installation of all ductwork to the SMACNA pressure class specified, including duct "
             "sealing, leakage testing, access doors, fire and smoke dampers, and turning vanes."
     },
    {"id": "d23.incl.curbs_supports", "division": "23", "category": "Scope",
     "title": "Curbs Supports", "default": True, "position": 30,
     "body": "Furnishing of all roof curbs, equipment rails, vibration isolation, housekeeping pad dimensions and "
             "structural support requirements, delivered in time for installation by the responsible trades."
     },
    {"id": "d23.incl.tab", "division": "23", "category": "Scope",
     "title": "Tab", "default": True, "position": 40,
     "body": "Testing, adjusting and balancing by an independent AABC or NEBB certified agency, including a full "
             "report, and return visits to rebalance following any post-report adjustments."
     },
    {"id": "d23.incl.controls", "division": "23", "category": "Scope",
     "title": "Controls", "default": True, "position": 50,
     "body": "Complete direct digital control system including controllers, sensors, actuators, valves, control "
             "wiring, graphics, point-to-point checkout, sequences of operation, programming and integration with the "
             "building automation system."
     },
    {"id": "d23.incl.startup", "division": "23", "category": "Scope",
     "title": "Startup", "default": True, "position": 60,
     "body": "Manufacturer start-up of all major equipment, submission of start-up reports, and correction of "
             "deficiencies identified during start-up and commissioning."
     },
    {"id": "d23.incl.temp_hvac", "division": "23", "category": "Scope",
     "title": "Temp Hvac", "default": False, "position": 70,
     "body": "Temporary conditioning of the building using permanent equipment where directed, including temporary "
             "filtration, extra filter changes, and refurbishment of equipment to as-new condition prior to turnover."
     },
    {"id": "d23.incl.duct_cleaning", "division": "23", "category": "Scope",
     "title": "Duct Cleaning", "default": False, "position": 80,
     "body": "Cleaning of all ductwork prior to turnover where the system was operated during construction, and "
             "replacement of all filters at Substantial Completion."
     },
    {"id": "d23.excl.electrical_power", "division": "23", "category": "Exclusions",
     "title": "Electrical Power", "default": True, "position": 200,
     "body": "Line-voltage power wiring, disconnects, starters and variable frequency drives, which are by the "
             "Electrical Subcontractor unless factory mounted on the equipment."
     },
    {"id": "d23.excl.structural_support", "division": "23", "category": "Exclusions",
     "title": "Structural Support", "default": True, "position": 210,
     "body": "Structural steel dunnage and reinforcement of the building structure to support HVAC equipment, which is "
             "by the Metals Subcontractor from loading information furnished under this Subcontract."
     },
    {"id": "d23.excl.gas_service", "division": "23", "category": "Exclusions",
     "title": "Gas Service", "default": False, "position": 220,
     "body": "Natural gas service, meter and piping to the building, which is by the utility company and the Site "
             "Utilities Subcontractor."
     },
    {"id": "d25.incl.integration", "division": "25", "category": "Scope",
     "title": "Integration", "default": True, "position": 10,
     "body": "Integration of mechanical, electrical, lighting, metering and life safety systems into a single "
             "supervisory platform, including all gateways, protocol translation, network configuration, graphics and "
             "trend logging."
     },
    {"id": "d25.incl.commissioning_support", "division": "25", "category": "Scope",
     "title": "Commissioning Support", "default": True, "position": 20,
     "body": "Support of the Commissioning Authority including point-to-point verification, trend data extraction, and "
             "demonstration of every sequence of operation."
     },
    {"id": "d25.excl.field_devices", "division": "25", "category": "Exclusions",
     "title": "Field Devices", "default": True, "position": 200,
     "body": "Field devices, sensors and control valves furnished under the mechanical and electrical Divisions. Their "
             "integration and configuration is included."
     },
    {"id": "d26.incl.complete_electrical", "division": "26", "category": "Scope",
     "title": "Complete Electrical", "default": True, "position": 10,
     "body": "Complete electrical systems including service entrance, switchgear, panelboards, transformers, feeders, "
             "branch circuits, wiring devices, lighting fixtures, lighting controls, grounding and bonding."
     },
    {"id": "d26.incl.utility_coordination", "division": "26", "category": "Scope",
     "title": "Utility Coordination", "default": True, "position": 20,
     "body": "Coordination with the serving electric utility, including submission of applications, provision of the "
             "utility-required conduit, ductbank, transformer pad, metering provisions and secondary connections."
     },
    {"id": "d26.incl.lighting_controls", "division": "26", "category": "Scope",
     "title": "Lighting Controls", "default": True, "position": 30,
     "body": "Complete lighting control system including occupancy sensors, daylight sensors, dimming controls, relay "
             "panels, programming, and the functional testing and documentation required by the energy code."
     },
    {"id": "d26.incl.generator", "division": "26", "category": "Scope",
     "title": "Generator", "default": False, "position": 40,
     "body": "Emergency and standby power systems including generator, automatic transfer switches, fuel system, "
             "exhaust, load bank testing and code-required acceptance testing."
     },
    {"id": "d26.incl.equipment_connections", "division": "26", "category": "Scope",
     "title": "Equipment Connections", "default": True, "position": 50,
     "body": "Line-voltage power, disconnects and final connections to all equipment furnished by other trades and by "
             "the Owner, based on approved shop drawings and equipment schedules."
     },
    {"id": "d26.incl.coordination_study", "division": "26", "category": "Scope",
     "title": "Coordination Study", "default": True, "position": 60,
     "body": "Short circuit, protective device coordination and arc flash hazard studies by a licensed professional "
             "engineer, with equipment labeling applied per the study results."
     },
    {"id": "d26.incl.testing_acceptance_elec", "division": "26", "category": "Scope",
     "title": "Testing Acceptance Elec", "default": True, "position": 70,
     "body": "Acceptance testing by a NETA certified agency for all specified equipment, including insulation "
             "resistance, ground resistance, breaker and relay testing, with a complete report submitted."
     },
    {"id": "d26.incl.temp_power", "division": "26", "category": "Scope",
     "title": "Temp Power", "default": False, "position": 80,
     "body": "Temporary power and temporary lighting for the Project, including distribution, maintenance, relocation "
             "as work proceeds, code-required GFCI protection, monthly inspection, and removal at completion."
     },
    {"id": "d26.incl.firestop_elec", "division": "26", "category": "Scope",
     "title": "Firestop Elec", "default": True, "position": 90,
     "body": "Firestopping of all electrical penetrations through rated assemblies using listed systems appropriate to "
             "the penetrant, and identification labeling at each location."
     },
    {"id": "d26.excl.low_voltage", "division": "26", "category": "Exclusions",
     "title": "Low Voltage", "default": True, "position": 200,
     "body": "Structured cabling, audio-visual, security and fire alarm systems, which are by the Division 27 and 28 "
             "Subcontractors. Conduit, back boxes and pull strings for those systems are included where shown."
     },
    {"id": "d26.excl.utility_fees", "division": "26", "category": "Exclusions",
     "title": "Utility Fees", "default": True, "position": 210,
     "body": "Utility company charges, aid-to-construction fees and transformer costs, which are paid directly by the "
             "Owner."
     },
    {"id": "d26.excl.equipment_furnish", "division": "26", "category": "Exclusions",
     "title": "Equipment Furnish", "default": False, "position": 220,
     "body": "Furnishing of mechanical equipment, starters and variable frequency drives, which are furnished by the "
             "Mechanical Subcontractor for connection under this Subcontract."
     },
    {"id": "d27.incl.structured_cabling", "division": "27", "category": "Scope",
     "title": "Structured Cabling", "default": True, "position": 10,
     "body": "Complete structured cabling system including horizontal and backbone cabling, patch panels, racks, cable "
             "management, grounding, labeling, testing and certification to the specified performance category."
     },
    {"id": "d27.incl.testing_certification", "division": "27", "category": "Scope",
     "title": "Testing Certification", "default": True, "position": 20,
     "body": "Testing of every copper and fiber link with a calibrated certification tester, submission of the full "
             "test results in electronic form, and a manufacturer's extended system warranty."
     },
    {"id": "d27.incl.pathways", "division": "27", "category": "Scope",
     "title": "Pathways", "default": True, "position": 30,
     "body": "Cable tray, J-hooks, sleeves, innerduct and firestopping of communications pathways, including all "
             "penetrations created by this trade."
     },
    {"id": "d27.incl.av", "division": "27", "category": "Scope",
     "title": "Av", "default": False, "position": 40,
     "body": "Audio-visual systems including displays, projectors, sound reinforcement, control systems, programming, "
             "calibration and Owner training."
     },
    {"id": "d27.excl.conduit_backboxes", "division": "27", "category": "Exclusions",
     "title": "Conduit Backboxes", "default": True, "position": 200,
     "body": "Conduit, back boxes, and line-voltage power to communications rooms and devices, which are by the "
             "Electrical Subcontractor."
     },
    {"id": "d27.excl.active_equipment", "division": "27", "category": "Exclusions",
     "title": "Active Equipment", "default": False, "position": 210,
     "body": "Owner-furnished active network equipment, switches, routers and servers. Rack space, patching and cable "
             "management for them are included."
     },
    {"id": "d28.incl.fire_alarm", "division": "28", "category": "Scope",
     "title": "Fire Alarm", "default": True, "position": 10,
     "body": "Complete fire alarm system including control panel, initiating devices, notification appliances, wiring, "
             "programming, battery calculations, voltage drop calculations, and permit drawings sealed as required by "
             "the authority having jurisdiction."
     },
    {"id": "d28.incl.fa_testing", "division": "28", "category": "Scope",
     "title": "Fa Testing", "default": True, "position": 20,
     "body": "100% device testing and final acceptance testing witnessed by the authority having jurisdiction, "
             "including the NFPA 72 record of completion and inspection and testing forms."
     },
    {"id": "d28.incl.interfaces", "division": "28", "category": "Scope",
     "title": "Interfaces", "default": True, "position": 30,
     "body": "All interfaces to other systems, including elevator recall and shunt trip, sprinkler tamper and flow "
             "monitoring, HVAC smoke control shutdown, door holder release and access control release on alarm."
     },
    {"id": "d28.incl.access_control", "division": "28", "category": "Scope",
     "title": "Access Control", "default": False, "position": 40,
     "body": "Access control system including controllers, readers, request-to-exit devices, door position switches, "
             "electrified hardware connection, software configuration, credential enrollment and Owner training."
     },
    {"id": "d28.incl.video", "division": "28", "category": "Scope",
     "title": "Video", "default": False, "position": 50,
     "body": "Video surveillance system including cameras, network video recorders, storage sized for the specified "
             "retention period, licensing, camera aiming and view documentation."
     },
    {"id": "d28.excl.conduit_power_sec", "division": "28", "category": "Exclusions",
     "title": "Conduit Power Sec", "default": True, "position": 200,
     "body": "Conduit, back boxes and line-voltage power, which are by the Electrical Subcontractor from the device "
             "locations furnished under this Subcontract."
     },
    {"id": "d28.excl.door_hardware", "division": "28", "category": "Exclusions",
     "title": "Door Hardware", "default": True, "position": 210,
     "body": "Furnishing of electrified door hardware, which is furnished by the Division 08 Subcontractor and "
             "connected under this Subcontract."
     },
    {"id": "d28.excl.monitoring", "division": "28", "category": "Exclusions",
     "title": "Monitoring", "default": False, "position": 220,
     "body": "Ongoing central station monitoring and communication service charges after Substantial Completion, which "
             "are contracted directly by the Owner."
     },
    {"id": "d31.incl.mass_excavation", "division": "31", "category": "Scope",
     "title": "Mass Excavation", "default": True, "position": 10,
     "body": "Clearing, grubbing, stripping, mass excavation, structural excavation, backfill, compaction and fine "
             "grading to the lines, grades and tolerances shown, including all cut-fill balancing on site."
     },
    {"id": "d31.incl.erosion_control", "division": "31", "category": "Scope",
     "title": "Erosion Control", "default": True, "position": 20,
     "body": "Installation and maintenance of all erosion and sedimentation control measures for the duration of the "
             "Work, including silt fence, inlet protection, construction entrances, weekly and post-rainfall "
             "inspections, SWPPP recordkeeping, and removal at stabilization."
     },
    {"id": "d31.incl.subgrade_prep", "division": "31", "category": "Scope",
     "title": "Subgrade Prep", "default": True, "position": 30,
     "body": "Proof-rolling and preparation of subgrade beneath slabs, pavements and footings, and furnishing, placing "
             "and compacting granular base to the thickness and density specified."
     },
    {"id": "d31.incl.shoring", "division": "31", "category": "Scope",
     "title": "Shoring", "default": True, "position": 40,
     "body": "Excavation support, sloping, benching, trench boxes and engineered shoring as required by OSHA and site "
             "conditions, designed by a licensed professional engineer where required."
     },
    {"id": "d31.incl.dewatering_incidental", "division": "31", "category": "Scope",
     "title": "Dewatering Incidental", "default": True, "position": 50,
     "body": "Surface water management and pumping of accumulated water from excavations, including sumps, discharge "
             "piping and required filtration prior to discharge."
     },
    {"id": "d31.incl.backfill_structures", "division": "31", "category": "Scope",
     "title": "Backfill Structures", "default": True, "position": 60,
     "body": "Backfill and compaction around foundations, walls, utility trenches and structures in controlled lifts, "
             "with density testing coordination and correction of any lift failing to meet the specified compaction."
     },
    {"id": "d31.incl.deep_foundations", "division": "31", "category": "Scope",
     "title": "Deep Foundations", "default": False, "position": 70,
     "body": "Deep foundation elements including drilled piers, augercast piles or driven piles, complete with "
             "installation records, pile driving logs and any required load testing."
     },
    {"id": "d31.incl.import_export", "division": "31", "category": "Scope",
     "title": "Import Export", "default": False, "position": 80,
     "body": "Import of suitable structural fill and export and legal disposal of surplus material, including all "
             "haul, tipping fees and permits."
     },
    {"id": "d31.excl.unsuitable_soils", "division": "31", "category": "Exclusions",
     "title": "Unsuitable Soils", "default": True, "position": 200,
     "body": "Undercut and replacement of unsuitable or unstable soils below the design subgrade elevation, which will "
             "be compensated at the unit prices stated in this Exhibit based on surveyed quantities."
     },
    {"id": "d31.excl.rock", "division": "31", "category": "Exclusions",
     "title": "Rock", "default": True, "position": 210,
     "body": "Rock excavation, blasting and removal of boulders exceeding one cubic yard, which will be compensated at "
             "the unit prices stated in this Exhibit."
     },
    {"id": "d31.excl.geotech_testing", "division": "31", "category": "Exclusions",
     "title": "Geotech Testing", "default": True, "position": 220,
     "body": "Owner's geotechnical testing agency for compaction and materials testing. Providing access and standing "
             "by during testing is included."
     },
    {"id": "d31.excl.contaminated_soil", "division": "31", "category": "Exclusions",
     "title": "Contaminated Soil", "default": True, "position": 230,
     "body": "Handling, transportation and disposal of contaminated soil or groundwater encountered on site."
     },
    {"id": "d31.excl.permanent_dewatering", "division": "31", "category": "Exclusions",
     "title": "Permanent Dewatering", "default": False, "position": 240,
     "body": "Engineered dewatering systems, well points and deep wells required to lower the groundwater table."
     },
    {"id": "d32.incl.paving", "division": "32", "category": "Scope",
     "title": "Paving", "default": True, "position": 10,
     "body": "Complete asphalt and concrete paving including aggregate base, binder and surface courses, curbs, "
             "gutters, sidewalks, ramps and pavement markings."
     },
    {"id": "d32.incl.ada", "division": "32", "category": "Scope",
     "title": "Ada", "default": True, "position": 20,
     "body": "Construction of all accessible routes, curb ramps, detectable warning surfaces and accessible parking to "
             "the running slope and cross slope tolerances required by the ADA, verified by survey prior to "
             "acceptance, and replacement of any non-compliant work at no additional cost."
     },
    {"id": "d32.incl.landscaping", "division": "32", "category": "Scope",
     "title": "Landscaping", "default": False, "position": 30,
     "body": "Landscaping including topsoil, soil amendments, planting, sod, seeding, mulch, tree staking, and a full "
             "establishment and maintenance period through the end of the warranty term."
     },
    {"id": "d32.incl.irrigation", "division": "32", "category": "Scope",
     "title": "Irrigation", "default": False, "position": 40,
     "body": "Complete irrigation system including mainline, laterals, heads, valves, controller, rain sensor, "
             "backflow prevention, winterization and coverage testing."
     },
    {"id": "d32.incl.fencing", "division": "32", "category": "Scope",
     "title": "Fencing", "default": False, "position": 50,
     "body": "Site fencing, gates, operators, bollards and site furnishings, complete with footings and final "
             "adjustment."
     },
    {"id": "d32.excl.subgrade_by_others", "division": "32", "category": "Exclusions",
     "title": "Subgrade By Others", "default": True, "position": 200,
     "body": "Preparation and certification of subgrade to within plus or minus one tenth of a foot, which is by the "
             "Earthwork Subcontractor."
     },
    {"id": "d32.excl.striping_maintenance", "division": "32", "category": "Exclusions",
     "title": "Striping Maintenance", "default": False, "position": 210,
     "body": "Re-striping and seal coating after Substantial Completion, and repair of pavement damaged by other "
             "trades after acceptance."
     },
    {"id": "d33.incl.site_utilities", "division": "33", "category": "Scope",
     "title": "Site Utilities", "default": True, "position": 10,
     "body": "Complete site utilities including sanitary sewer, storm drainage, domestic and fire water mains, "
             "structures, manholes, inlets, cleanouts, fittings, valves, thrust restraint, bedding and backfill, from "
             "the point of connection to five feet outside the building line."
     },
    {"id": "d33.incl.testing_utilities", "division": "33", "category": "Scope",
     "title": "Testing Utilities", "default": True, "position": 20,
     "body": "All required testing including pressure and leakage testing, disinfection and bacteriological sampling "
             "of water mains, mandrel and vacuum testing of sewers, and video inspection of gravity lines with "
             "recordings submitted."
     },
    {"id": "d33.incl.tie_ins", "division": "33", "category": "Scope",
     "title": "Tie Ins", "default": True, "position": 30,
     "body": "Connections and tie-ins to existing utilities, including coordination with the utility owner, required "
             "shutdowns, temporary bypass pumping, night and weekend work necessary to obtain a shutdown window, and "
             "restoration of disturbed areas."
     },
    {"id": "d33.incl.record_survey", "division": "33", "category": "Scope",
     "title": "Record Survey", "default": True, "position": 40,
     "body": "Record survey of all installed utilities by a licensed surveyor, showing horizontal location, invert "
             "elevations and material, in the format required by the authority having jurisdiction."
     },
    {"id": "d33.incl.stormwater", "division": "33", "category": "Scope",
     "title": "Stormwater", "default": False, "position": 50,
     "body": "Stormwater detention and retention structures, underground storage systems, outlet control structures, "
             "water quality units and their required maintenance access."
     },
    {"id": "d33.excl.utility_fees_33", "division": "33", "category": "Exclusions",
     "title": "Utility Fees 33", "default": True, "position": 200,
     "body": "Tap fees, impact fees, meter fees and utility company charges, which are paid directly by the Owner."
     },
    {"id": "d33.excl.building_side", "division": "33", "category": "Exclusions",
     "title": "Building Side", "default": True, "position": 210,
     "body": "Utilities inside the building line, which are by the Plumbing and Electrical Subcontractors."
     },
    {"id": "d33.excl.offsite", "division": "33", "category": "Exclusions",
     "title": "Offsite", "default": False, "position": 220,
     "body": "Offsite utility improvements, roadway restoration beyond the limits of disturbance, and municipal permit "
             "fees for work in the public right of way."
     },
]
