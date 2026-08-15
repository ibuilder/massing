r"""Parsing XML from a stranger, with only the standard library.

(Raw docstring: it quotes the old regex below, and `\[` in a plain string is an
invalid escape sequence -- a warning that this project turns into an error.)

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
no reason to define macros -- so this rejects attacks and not files.

Why this is not a regex any more
--------------------------------
It was one, and the regex was wrong in two ways that a reader would have to
know XML's grammar to see. `<!DOCTYPE[^>\[]*\[[^\]]*<!ENTITY` walks the internal
subset with `[^\]]*`, so **any** `]` before the declaration ends the match --
and a `]` is ordinary text inside a comment, which meant
`<!DOCTYPE r [<!-- ] -->` smuggled the whole bomb past. The scan was also capped
at the first 64KB, so 70KB of comment padding pushed the declaration out of the
window. Both were measured expanding, not argued about.

The fix is to stop lexing XML by hand. Expat already knows where the internal
subset starts and ends, which strings are quoted and which brackets are inside
comments, and it reports an entity declaration through `EntityDeclHandler` at
*declaration* time -- strictly before any reference to it could be expanded.
Raising from `StartElementHandler` stops the scan at the root element, because
that is the point past which a DTD cannot legally appear. So the scan is still
bounded to the prologue; it is bounded by the grammar now rather than by a byte
count that an attacker chooses the other side of.
"""

from __future__ import annotations

from xml.etree import ElementTree
from xml.parsers import expat


class _StopScanning(Exception):  # noqa: N818 - control flow, not an error
    """Raised inside an expat handler to abandon the parse early."""


def looks_like_a_bomb(content: str | bytes) -> bool:
    """True when the prologue declares XML entities.

    Separate from :func:`parse` so a caller that already has its own error type
    can ask the question without catching an exception to get an answer.
    """
    text_content = content.decode("utf-8", "replace") if isinstance(content, bytes) else content
    parser = expat.ParserCreate()
    declared = False

    def on_entity_declaration(*_: object) -> None:
        nonlocal declared
        declared = True
        raise _StopScanning

    def on_root_element(*_: object) -> None:
        # The DTD is over. Nothing after this can be a declaration, so there is
        # no reason to read the remaining 60MB of a real export.
        raise _StopScanning

    parser.EntityDeclHandler = on_entity_declaration
    parser.StartElementHandler = on_root_element
    try:
        parser.Parse(text_content, True)
    except _StopScanning:
        pass
    except expat.ExpatError:
        # Malformed. Not this function's question to answer -- say "no bomb"
        # and let the real parse fail with a message about what is wrong.
        pass
    return declared


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
#:
#: This is the exact complement of the `Char` production, and it was previously
#: wrong in *both* directions -- which is the shape of mistake that survives,
#: because the over-removal hides the under-removal in casual testing:
#:
#: * It missed the lone surrogates and U+FFFE/U+FFFF. Those are the same
#:   total-loss bug the module exists to prevent, and worse: U+FFFE produced an
#:   unopenable file, while a lone surrogate raised `UnicodeEncodeError` out of
#:   the *encode*, so the export failed with a traceback about a codec.
#: * It removed U+007F and U+0080-U+009F, which XML 1.0 permits. The spec
#:   discourages them; discouraged is not forbidden, and quietly replacing a
#:   character the planner typed is the silent defaulting this codebase refuses
#:   everywhere else. They are round-tripped by a test rather than assumed safe.
_ILLEGAL = (
    {codepoint for codepoint in range(0x20) if codepoint not in (0x09, 0x0A, 0x0D)}
    | set(range(0xD800, 0xE000))
    | {0xFFFE, 0xFFFF}
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
