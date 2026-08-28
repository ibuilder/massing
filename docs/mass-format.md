# The `.mass` project container

**Format id** `massing.project` · **version** 2 · **media type** `application/zip`

A `.mass` file is one project: its model, all of its data, and its attachments, in a single file you
can copy, email, archive or check into version control. It is a **plain ZIP archive**. Everything
inside is either UTF-8 JSON or a standard AEC file format. There is no proprietary encoding anywhere,
and you do not need Massing to read it.

## Why it is called that

It was `.mmproj` through version 1. That name read as *Microsoft Project* to people who had never
seen it, which is the opposite of what it is — this container has never held a byte of XML or any
vendor format. An extension that misleads about its own contents is a defect, so it became `.mass`.

**Version 1 `.mmproj` files still open.** A rename that orphans everything anyone already saved is
not a rename; it is data loss. Massing reads v1 forever and writes v2 only.

## Layout

```
project.mass                 (ZIP)
├── manifest.json            what this container is + a full inventory + what was excluded
├── README.txt               plain-English explanation, written INSIDE the file
├── project.json             id, name, origin, source IFC file name
├── asset_rights.json        OPTIONAL - a signed release manifest, only if the person who
│                            created the file asked for one (see below)
├── data/<table>.json        one file per table; a JSON array of row objects, keys = column names
├── geometry/
│   ├── <name>.ifc           the source model — open it with any IFC tool
│   └── model.frag           pre-converted geometry tile for fast viewing (derived, regenerable)
└── blobs/<storage key>      file attachments under their original keys
```

The README is written into the archive on purpose. **Documentation that lives in a repository is
documentation the person holding the file does not have** — somebody who unzips this in ten years
with none of our software should be able to work out what they are holding.

## How to decipher one

Without any of our code:

1. **Unzip it.** It is an ordinary ZIP.
2. **Read `README.txt`.** It describes the layout in plain English.
3. **Read `manifest.json`** for the format id, version, an inventory of every entry with its size,
   and — the field most containers omit — `excluded`, naming what deliberately did *not* travel.
4. **Open `geometry/*.ifc`** in any IFC viewer. That is the source of truth for the building.
5. **Read `data/*.json`** as ordinary JSON arrays. Rows reference building elements by **IFC
   GlobalId**, never by a viewer-local or database-local id, so any row can be tied back to an element
   in the IFC — across exports and across tools.

## `manifest.json`

| Field | Meaning |
|---|---|
| `format` | `massing.project` |
| `version` | `2` |
| `extension` | `.mass` |
| `exported_at` | UTC ISO-8601 |
| `project` | `{id, name}` at export time |
| `tables` | row count per table actually written |
| `has_frag` | whether a pre-converted geometry tile is present |
| `has_asset_rights` | whether the optional "asset_rights.json" entry is present — see [Sealing](#sealing-a-container-optional) |
| `entries` | every path in the archive with its uncompressed size |
| `excluded` | `{tables, why}` — see below |
| `reads` | the format versions this build accepts |

## What is deliberately excluded

`users`, `audit_log`, `app_settings`, `connections` and the migration marker never travel.

They are **account- or machine-specific**: they belong to an installation, not to a project, and
importing them would overwrite the destination's own accounts and credentials. This is listed in
`excluded` with the reason rather than left to be discovered, because **a container that silently
drops them looks complete and is not**.

## Sealing a container (optional)

A `.mass` can be **sealed** with a release manifest, the "asset_rights.json" entry. It is **opt-in
and chosen when the file is created**, because a manifest attests to the bytes of one particular
export — it cannot be bolted on afterwards without producing a different file. A container saved
without it is byte-for-byte what this format has always produced, and the manifest field
`has_asset_rights` says which kind you are holding.

What it contains:

* `content_hash` — the **identity** of the release: a SHA-256 over the payload entries
  ("project.json", `data/`, the source IFC, "index/props.json", `blobs/`), each listed with its own
  hash and byte length. It excludes every volatile value — timestamps, ids, the signature itself —
  so the same release computes the same hash on any machine, in any build, at any time.
* `derived` — regenerable artifacts, recorded but **deliberately outside identity**. `model.frag` is
  derived from the IFC, so re-converting it must not read as a new release.
* `verification` — an **Ed25519** signature over the manifest, present only when the issuer had a
  signing key configured. Verify it with the issuer's *published* public key: the key inside the
  file only proves the file agrees with itself, which an attacker who rewrote it would also arrange.

**What it does not cover**, stated because an unstated boundary is the defect: `manifest.json` and
`README.txt` are regenerated description carrying an export timestamp, not project data, and are
outside the attestation.

**A re-import followed by a re-export produces a different `content_hash`**, because importing
regenerates the project id and every row primary key by design (see Import rules below). That is why
there are two identifiers: the project asset id says two containers are the same asset,
`content_hash` says this is one particular published release of it. The asset id is the one value
import carries across verbatim.

## Import rules

* **A fresh project id is minted** on every import, and row primary keys are regenerated (with
  `topic_id` and module `record_id` foreign keys remapped). A container can therefore be cloned into
  the same database, or moved to another machine, without collisions.
* **A container from a newer build is refused, not partially read.** It may hold structures an older
  build would silently misinterpret, and a half-imported project is worse than a declined one: the
  user believes they have their data.
* **An unrecognised format id is refused**, and the error names what was expected.

## Relationship to ISO 21597 (ICDD)

`.mass` is a bespoke container today. The intended direction is that it becomes an
**[ISO 21597](https://www.iso.org/standard/74389.html) Information Container for linked Document
Delivery** — payload documents plus RDF linksets — so a `.mass` *is* a standards-conformant ICDD
container carrying our extension, rather than a format only we can read. That is tracked as
**R28-ICDD** in [roadmap.md](roadmap.md); `rdflib` (BSD-3) is approved for it, and the licensing is
recorded in [ATTRIBUTIONS.md](ATTRIBUTIONS.md).

The reasoning is the same bet this platform already made with BCF: **a bespoke container round-trips
with nothing; a standard one round-trips with everyone.**

## Related formats we read but do not store in

Schedules arrive as Primavera P6 `.xer` (tab-delimited) or PMXML, or Microsoft Project MSPDI XML.
Those are **import on-ramps**, not storage — every real contractor has one of those tools, and
refusing to read their file means refusing the customer. `.mpp` is deliberately unsupported: it is a
proprietary binary, and the right answer is to export XER or CSV.

Once imported, a schedule lives in the model as native IFC 4D — `IfcWorkSchedule` / `IfcTask` /
`IfcTaskTime`, bound to elements by `IfcRelAssignsToProduct` — so it travels inside the IFC and any
openBIM tool can read it. **That is the modern, standard, vendor-neutral home for schedule data, and
it is where ours lives.**
