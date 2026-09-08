"""Which language a pasted goods line is written in.

This decides which language the derived description comes back in — "Hoekprofiel
staal 80×80×8×6000", "Steel angle profile …" or "Stahl Winkelprofil …". It is a
guess on keywords and no more than that; the user can always overwrite the
description.

Recognition of the materials themselves runs via the catalogue's synonym list,
and that does not yet know German terms. What this detection solves is only the
language of what EMCargo writes back.
"""

KEYWORDS = {
    "nl": {"staal", "stalen", "hoekprofiel", "kokerprofiel", "gegalvaniseerd",
           "verzinkt", "hout", "beton", "aantal", "stuks", "lengte"},
    "en": {"steel", "angle", "profile", "galvanized", "galvanised", "wood",
           "concrete", "quantity", "length", "pieces"},
    # "verzinkt" and "beton" are in the Dutch list too. That is not an error but
    # a tie, and a tie goes to Dutch.
    "de": {"stahl", "winkelprofil", "quadratrohr", "verzinkt", "holz", "beton",
           "menge", "stück", "länge", "blech", "träger", "rundstab"},
    # "beton" and "profil" occur in more than one language; here too a tie goes
    # to Dutch.
    "fr": {"acier", "cornière", "tube", "galvanisé", "bois", "béton",
           "quantité", "longueur", "pièces", "tôle", "poutre", "profilé"},
}

# On a tie the language listed first wins: the one in which the data is most
# complete.
_ORDER = ("nl", "en", "de", "fr")


def detect_language(text: str) -> str:
    lower = str(text or "").lower()
    counts = {lang: sum(1 for word in words if word in lower)
              for lang, words in KEYWORDS.items()}
    return max(_ORDER, key=lambda lang: (counts[lang], -_ORDER.index(lang)))
