"""Parsing XML from a stranger, with only the standard library.

Both file readers take a document somebody uploaded. `defusedxml` is the usual
answer and `core` cannot have it -- the subtree is pure standard library by
contract, because it is copied verbatim into another codebase. So the defence
has to be built from what is here.

What was actually wrong
-----------------------
`xml.etree.ElementTree` does not resolve *external* entities, which is the
attack most people mean by "XXE". It does expand **internal** ones, and that
was measured rather than assumed: a 448-byte document with four levels of
nested entity definitions expanded to 30,000 characters. Each level multiplies
by ten, so nine levels is about three gigabytes from a payload small enough to
fit in a tweet.

The reader carried a note saying the application layer hardened untrusted
uploads. It does not -- the only control is a byte limit on the upload, and a
billion-laughs payload is tiny by construction. The note described a defence
nobody had built, which is worse than no note: it is a reason not to look.

The defence
-----------
Refuse a document type declaration that defines entities, before parsing.
Neither Primavera nor MS Project writes one -- an export is generated data with
no reason to define macros -- so this rejects attacks and not files. The check
is on the raw text because by the time a parser has produced a tree the
expansion has already happened, and it is bounded to the head of the document
because a DTD is only legal there.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree

#: A DOCTYPE with an internal subset that declares entities. Both parts matter:
#: a bare `<!DOCTYPE plan SYSTEM "x.dtd">` cannot expand anything through
#: ElementTree, which ignores external DTDs, so refusing every DOCTYPE would
#: reject harmless documents to no purpose.
_ENTITY_DECLARATION = re.compile(rb"<!DOCTYPE[^>\[]*\[[^\]]*<!ENTITY", re.IGNORECASE | re.DOTALL)

#: A DTD is only legal before the root element, so there is no reason to scan a
#: 60MB export to its end looking for one -- and every reason not to, on a path
#: that runs for every upload.
_PROLOGUE_BYTES = 64 * 1024


def looks_like_a_bomb(content: str | bytes) -> bool:
    """True when the prologue declares XML entities.

    Separate from :func:`parse` so a caller that already has its own error type
    can ask the question without catching an exception to get an answer.
    """
    raw = content.encode("utf-8", "replace") if isinstance(content, str) else content
    return bool(_ENTITY_DECLARATION.search(raw[:_PROLOGUE_BYTES]))


def parse(content: str) -> ElementTree.Element:
    """Parse a document from an untrusted source, or raise ``ValueError``.

    Callers wrap the failure in their own format's error type, so the message
    a user sees names the format they thought they were uploading.
    """
    if looks_like_a_bomb(content):
        raise ValueError(
            "this document declares XML entities in its document type "
            "declaration. Primavera and MS Project do not write those, and "
            "nested entity definitions are how a small file expands into "
            "gigabytes while it is being read, so it is refused unparsed"
        )
    # Safe now: the expansion vector is gone, and ElementTree does not resolve
    # external entities at all.
    return ElementTree.fromstring(content)  # noqa: S314 - guarded immediately above


#: Characters XML 1.0 does not permit in content **at any escaping**.
#:
#: The rule is `#x9 | #xA | #xD | [#x20-#xD7FF] | ...`, so every other C0
#: control is simply not expressible: `&#x0B;` is as illegal as a raw vertical
#: tab. `xml.sax.saxutils.escape` does not help -- it handles `&`, `<` and `>`,
#: which are the characters that change a document's *meaning*, and says
#: nothing about the ones that make it unparseable.
#:
#: An activity named `Dig<VT>vertical` therefore produced an export that no XML
#: parser would open, including MS Project's and P6's. Not tampering: total
#: loss, discovered when the planner tries to open the file.
_ILLEGAL = (
    {codepoint for codepoint in range(0x20) if codepoint not in (0x09, 0x0A, 0x0D)}
    | {0x7F}
    | set(range(0x80, 0xA0))
)

_ILLEGAL_TABLE = dict.fromkeys(_ILLEGAL, " ")


def text(value: str) -> str:
    """A string safe to place in XML content, with illegal characters removed.

    Replaced with a space rather than dropped, on the same reasoning as the XER
    writer: `Level 1<VT>Walls` should stay two words. Escaping is not deleting,
    and a writer that silently swallowed the planner's activity names would be
    trading one bug for a quieter one.

    This is *not* a substitute for escaping `&`, `<` and `>` -- the writers do
    that separately, and the two solve different problems. This one is about
    documents that will not parse; that one is about documents that parse into
    something else.
    """
    return value.translate(_ILLEGAL_TABLE)


__all__ = ["looks_like_a_bomb", "parse", "text"]
