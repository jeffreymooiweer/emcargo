"""What outgoing mail says, in the reader's language and in two forms.

Three rules hold this module together.

**The language belongs to the reader, not to the sender.** A colleague whose
EMCargo is in German gets a German invitation, even when the
administrator who made the account works in Dutch. Where the reader has no
preference yet — a brand-new account — the installation's default language
is the honest guess.

**Every message is both plain text and HTML.** The HTML carries the logo and
reads like a letter; the plain text is what a mail client that refuses HTML,
a screen reader, or a phone on a bad connection falls back to. Neither is a
degraded version of the other: both say the same thing.

**Nothing is said that the reader does not need to know.** The invitation
used to name the administrator who sent it, which handed an administrator's
user name to anybody who received an invitation — including anyone who
should not have one. It says "an administrator" now.
"""
from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path

from app.core.languages import normalise

#: The logo, beside the backend rather than in the frontend's build output:
#: mail is sent by the server, and a server that reads from a directory only
#: the frontend build fills would send logo-less mail the day that changes.
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"

#: The Content-ID the HTML refers to. A related part rather than a data: URI
#: or a link: Gmail and Outlook both drop data: images, and a linked one
#: means the reader's mail client calls this server — which is a tracking
#: pixel by accident, and a broken image on an installation that is not
#: reachable from the internet.
LOGO_CID = "emcargo-logo"


#: The copy glyph beside a sign-in code. A PNG rather than the inline SVG the
#: interface uses, because Gmail strips ``<svg>`` from mail outright; it is the
#: application's own drawing, rendered by scripts/render_mail_icons.py from the
#: same paths as icons.tsx, so no third-party licence travels here.
COPY_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "copy.png"
COPY_ICON_CID = "emcargo-copy"


@lru_cache(maxsize=1)
def _default_logo() -> bytes | None:
    """EMCargo's own logo, or nothing when it is missing.

    Missing is survivable: the message still says everything it needs to.
    A crash while somebody is resetting their password is not.
    """
    try:
        return LOGO_PATH.read_bytes()
    except OSError:
        return None


def logo_image() -> tuple[bytes, str] | None:
    """The logo the mail carries, as ``(bytes, MIME subtype)``.

    The installation's own when an administrator uploaded one — the mail
    should look like the screen it came from — and EMCargo's otherwise.
    Read fresh rather than cached, because the uploaded one can change while
    the process runs and a mail with last month's logo is a small lie.
    """
    from app.services import branding

    custom = branding.logo_image()
    if custom:
        return custom
    default = _default_logo()
    return (default, "png") if default else None


def logo_bytes() -> bytes | None:
    image = logo_image()
    return image[0] if image else None


@lru_cache(maxsize=1)
def copy_icon_bytes() -> bytes | None:
    """The copy glyph, or nothing when it is missing.

    Survivable in the same way, and more so: the glyph is a hint about how to
    reach the code, never the code itself. Without it the message still shows
    six digits and still says to hold them.
    """
    try:
        return COPY_ICON_PATH.read_bytes()
    except OSError:
        return None


def layout(language: str, heading: str, paragraphs: list[str],
           button: tuple[str, str] | None = None,
           block: str | None = None,
           block_hint: str = "",
           footer: str = "") -> str:
    """One letter, as HTML that survives the mail clients people use.

    Tables and inline styles, deliberately: Outlook renders with Word, which
    has no flexbox, no grid and no external stylesheet. This is 2003 markup
    on purpose, because it is what arrives intact.

    **The viewport meta is the load-bearing line.** Without it a mail client
    lays the message out in a desktop-width container — Gmail on Android
    assumes about 980 pixels — and then shows the phone a slice of that.
    Measured in a 980-pixel container, this card is centred starting at
    x=210: a wide empty margin on the left and the card running off the
    right, which is exactly what the first reader of an invitation saw on
    their phone. Declaring ``width=device-width`` is what makes the client
    lay it out at the width it actually has.

    The rest is not what caused that, and is here because it is what makes
    a message render the same everywhere:

    * **no padding on ``<body>``**: Gmail lifts the content into its own
      container and drops body styles, so the gutter is a cell of a wrapper
      table instead;
    * **centring by ``align="center"``** as well as ``max-width``, because
      Word (which renders Outlook) ignores ``margin:0 auto``;
    * **a long URL that may break anywhere**, so a 60-character token cannot
      set a minimum width for the whole table.
    """
    body: list[str] = []
    for text in paragraphs:
        body.append(
            f'<p style="margin:0 0 16px;font-size:15px;line-height:1.55;'
            f'color:#0f172a;">{text}</p>'
        )
    if block:
        # The code sits in a cell of its own, with the glyph in the next one
        # rather than inside it. That is not decoration: a mail client cannot
        # copy anything — there is no JavaScript and no clipboard API in
        # e-mail — so what actually puts this code on the clipboard is the
        # reader holding their finger on it. Keeping the image out of the
        # code's own cell keeps that press selecting six digits and nothing
        # else, and the glyph beside it says which six digits to press.
        icon = (f'<td valign="middle" style="padding:14px 18px 14px 0;">'
                f'<img src="cid:{COPY_ICON_CID}" width="18" height="18" alt="" '
                'style="display:block;border:0;width:18px;height:18px;" />'
                '</td>') if copy_icon_bytes() else ""
        body.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" '
            'border="0" align="center" style="margin:0 auto 8px;'
            'background:#f1f5f9;border-radius:10px;"><tr>'
            f'<td style="padding:14px {"6px" if icon else "18px"} 14px 18px;'
            'font-family:ui-monospace,Menlo,Consolas,monospace;font-size:22px;'
            f'letter-spacing:3px;color:#0f172a;">{block}</td>'
            f'{icon}</tr></table>'
        )
    if block_hint:
        body.append(
            '<p style="margin:0 0 16px;font-size:12px;line-height:1.5;'
            f'color:#64748b;text-align:center;">{block_hint}</p>'
        )
    if button:
        label, href = button
        body.append(
            f'<p style="margin:0 0 16px;"><a href="{escape(href, quote=True)}" '
            'style="display:inline-block;padding:12px 22px;background:#2563eb;'
            'color:#ffffff;text-decoration:none;border-radius:10px;'
            f'font-size:15px;font-weight:600;">{label}</a></p>'
            # The same address in full, because a button is unclickable in
            # some clients and unreadable when the message is forwarded as
            # text. Three wrapping rules because no single one is honoured
            # everywhere, and a link that cannot wrap widens the message.
            f'<p style="margin:0 0 16px;font-size:12px;line-height:1.5;'
            'color:#64748b;word-break:break-all;overflow-wrap:anywhere;'
            f'word-wrap:break-word;">{escape(href)}</p>'
        )
    if footer:
        body.append(
            f'<p style="margin:24px 0 0;padding-top:16px;'
            'border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;">'
            f'{footer}</p>'
        )

    logo = (f'<img src="cid:{LOGO_CID}" width="40" height="40" alt="EMCargo" '
            'style="display:block;border:0;width:40px;height:40px;" />'
            ) if logo_bytes() else ""

    return (
        '<!doctype html>'
        f'<html lang="{escape(language)}">'
        '<head>'
        '<meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width,initial-scale=1" />'
        '<meta name="color-scheme" content="light dark" />'
        '</head>'
        '<body style="margin:0;padding:0;background:#f1f5f9;'
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">'
        # The wrapper holds the background and the gutter, in a cell rather
        # than on the body, so it survives the clients that drop body styles.
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'width="100%" style="width:100%;background:#f1f5f9;">'
        '<tr><td align="center" style="padding:16px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'align="center" width="100%" style="width:100%;max-width:560px;'
        'background:#ffffff;border-radius:16px;border:1px solid #e2e8f0;">'
        '<tr><td style="padding:24px 24px 8px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0">'
        f'<tr><td style="padding-right:10px;">{logo}</td>'
        '<td style="font-size:18px;font-weight:600;color:#0f172a;">EMCargo</td>'
        '</tr></table>'
        '</td></tr>'
        '<tr><td style="padding:8px 24px 24px;">'
        f'<h1 style="margin:0 0 16px;font-size:20px;line-height:1.3;'
        f'color:#0f172a;">{heading}</h1>'
        + "".join(body) +
        '</td></tr></table>'
        '</td></tr></table>'
        '</body></html>'
    )


def _text(paragraphs: list[str], link: str = "", block: str = "",
          footer: str = "") -> str:
    """The same letter as plain text, for whatever cannot show the HTML."""
    parts = list(paragraphs)
    if block:
        parts.append(f"    {block}")
    if link:
        parts.append(link)
    if footer:
        parts.append(footer)
    return "\n\n".join(parts) + "\n"


# --- the messages -----------------------------------------------------------
#
# Written out per language rather than assembled from fragments. A sentence
# translates; half a sentence plus a variable does not, and the four
# languages here put their nouns, verbs and politeness in different places.

RESET = {
    "nl": {
        "subject": "Wachtwoord opnieuw instellen",
        "heading": "Nieuw wachtwoord instellen",
        "intro": "Er is gevraagd om het wachtwoord van het EMCargo-account "
                 "'{username}' opnieuw in te stellen.",
        "action": "Kies een nieuw wachtwoord",
        "validity": "De link werkt één keer en vervalt na {minutes} minuten.",
        "ignore": "Heeft u dit niet aangevraagd? Dan is er niets gebeurd en "
                  "kunt u dit bericht negeren. Uw huidige wachtwoord blijft werken.",
    },
    "en": {
        "subject": "Reset your password",
        "heading": "Set a new password",
        "intro": "Somebody asked to reset the password of the EMCargo "
                 "account '{username}'.",
        "action": "Choose a new password",
        "validity": "The link works once and expires in {minutes} minutes.",
        "ignore": "If this was not you, nothing has happened and you can "
                  "ignore this message. Your current password still works.",
    },
    "de": {
        "subject": "Passwort zurücksetzen",
        "heading": "Neues Passwort festlegen",
        "intro": "Es wurde angefragt, das Passwort des EMCargo-Kontos "
                 "'{username}' zurückzusetzen.",
        "action": "Neues Passwort wählen",
        "validity": "Der Link gilt einmal und verfällt in {minutes} Minuten.",
        "ignore": "Waren Sie das nicht? Dann ist nichts geschehen und Sie "
                  "können diese Nachricht ignorieren. Ihr aktuelles Passwort "
                  "gilt weiterhin.",
    },
    "fr": {
        "subject": "Réinitialiser votre mot de passe",
        "heading": "Définir un nouveau mot de passe",
        "intro": "Quelqu'un a demandé la réinitialisation du mot de passe du "
                 "compte EMCargo « {username} ».",
        "action": "Choisir un nouveau mot de passe",
        "validity": "Le lien fonctionne une fois et expire dans {minutes} minutes.",
        "ignore": "Si ce n'était pas vous, rien ne s'est produit et vous "
                  "pouvez ignorer ce message. Votre mot de passe actuel reste "
                  "valable.",
    },
}

INVITE = {
    "nl": {
        "subject": "Uw EMCargo-account",
        "heading": "Welkom bij EMCargo",
        # No name: an invitation should not tell its reader which account is
        # an administrator's.
        "intro": "Een beheerder heeft een EMCargo-account voor u aangemaakt.",
        "username": "Uw gebruikersnaam is <strong>{username}</strong>.",
        "username_text": "Uw gebruikersnaam is {username}.",
        "action": "Kies uw wachtwoord",
        "validity": "De link werkt één keer en vervalt na {days} dagen.",
        "expired": "Daarna vraagt u op het inlogscherm met "
                   "'Wachtwoord vergeten?' een nieuwe link aan.",
    },
    "en": {
        "subject": "Your EMCargo account",
        "heading": "Welcome to EMCargo",
        "intro": "An administrator has made a EMCargo account for you.",
        "username": "Your user name is <strong>{username}</strong>.",
        "username_text": "Your user name is {username}.",
        "action": "Choose your password",
        "validity": "The link works once and expires in {days} days.",
        "expired": "After that, use 'Forgot your password?' on the sign-in "
                   "screen to get a new one.",
    },
    "de": {
        "subject": "Ihr EMCargo-Konto",
        "heading": "Willkommen bei EMCargo",
        "intro": "Ein Administrator hat ein EMCargo-Konto für Sie angelegt.",
        "username": "Ihr Benutzername lautet <strong>{username}</strong>.",
        "username_text": "Ihr Benutzername lautet {username}.",
        "action": "Passwort wählen",
        "validity": "Der Link gilt einmal und verfällt in {days} Tagen.",
        "expired": "Danach fordern Sie über „Passwort vergessen?“ auf der "
                   "Anmeldeseite einen neuen Link an.",
    },
    "fr": {
        "subject": "Votre compte EMCargo",
        "heading": "Bienvenue dans EMCargo",
        "intro": "Un administrateur a créé un compte EMCargo pour vous.",
        "username": "Votre nom d'utilisateur est <strong>{username}</strong>.",
        "username_text": "Votre nom d'utilisateur est {username}.",
        "action": "Choisir votre mot de passe",
        "validity": "Le lien fonctionne une fois et expire dans {days} jours.",
        "expired": "Ensuite, utilisez « Mot de passe oublié ? » sur la page "
                   "de connexion pour en obtenir un nouveau.",
    },
}

SIGN_IN_CODE = {
    "nl": {
        "subject": "Uw inlogcode",
        "heading": "Uw inlogcode",
        "intro": "Gebruik deze code om in te loggen bij EMCargo:",
        "hint": "Houd de code even ingedrukt om hem te kopiëren.",
        "validity": "De code vervalt na {minutes} minuten.",
        "warning": "Logt u nu niet in? Dan kent iemand anders uw wachtwoord. "
                   "Wijzig het en waarschuw de beheerder van EMCargo.",
    },
    "en": {
        "subject": "Your sign-in code",
        "heading": "Your sign-in code",
        "intro": "Use this code to sign in to EMCargo:",
        "hint": "Press and hold the code to copy it.",
        "validity": "The code expires in {minutes} minutes.",
        "warning": "If you are not signing in right now, somebody knows your "
                   "password. Change it, and tell whoever looks after EMCargo.",
    },
    "de": {
        "subject": "Ihr Anmeldecode",
        "heading": "Ihr Anmeldecode",
        "intro": "Verwenden Sie diesen Code, um sich bei EMCargo anzumelden:",
        "hint": "Halten Sie den Code gedrückt, um ihn zu kopieren.",
        "validity": "Der Code verfällt in {minutes} Minuten.",
        "warning": "Melden Sie sich gerade nicht an? Dann kennt jemand Ihr "
                   "Passwort. Ändern Sie es und informieren Sie den "
                   "Administrator von EMCargo.",
    },
    "fr": {
        "subject": "Votre code de connexion",
        "heading": "Votre code de connexion",
        "intro": "Utilisez ce code pour vous connecter à EMCargo :",
        "hint": "Maintenez le code appuyé pour le copier.",
        "validity": "Le code expire dans {minutes} minutes.",
        "warning": "Si vous n'êtes pas en train de vous connecter, quelqu'un "
                   "connaît votre mot de passe. Changez-le et prévenez "
                   "l'administrateur de EMCargo.",
    },
}

TEST = {
    "nl": {
        "subject": "EMCargo testbericht",
        "heading": "Het werkt",
        "intro": "Dit is een testbericht van EMCargo.",
        "explain": "Leest u dit, dan kloppen de instellingen van de "
                   "mailserver: EMCargo bereikte de server, werd "
                   "geaccepteerd en het bericht is bezorgd.",
    },
    "en": {
        "subject": "EMCargo test message",
        "heading": "It works",
        "intro": "This is a test message from EMCargo.",
        "explain": "If you are reading it, the mail server settings work: "
                   "EMCargo reached the server, was accepted, and the "
                   "message was delivered.",
    },
    "de": {
        "subject": "EMCargo-Testnachricht",
        "heading": "Es funktioniert",
        "intro": "Dies ist eine Testnachricht von EMCargo.",
        "explain": "Wenn Sie sie lesen, stimmen die Einstellungen des "
                   "Mailservers: EMCargo hat den Server erreicht, wurde "
                   "akzeptiert, und die Nachricht wurde zugestellt.",
    },
    "fr": {
        "subject": "Message de test EMCargo",
        "heading": "Cela fonctionne",
        "intro": "Ceci est un message de test de EMCargo.",
        "explain": "Si vous le lisez, les paramètres du serveur de messagerie "
                   "sont corrects : EMCargo a joint le serveur, a été "
                   "accepté, et le message a été distribué.",
    },
}

DOCUMENTS = {
    "nl": {
        "subject": "Vervoerdocumenten {reference}",
        "heading": "Vervoerdocumenten",
        "intro": "In de bijlage vindt u de vervoerdocumenten van deze zending.",
        "sender": "Verstuurd vanuit EMCargo door {sender}.",
    },
    "en": {
        "subject": "Transport documents {reference}",
        "heading": "Transport documents",
        "intro": "The transport documents for this consignment are attached.",
        "sender": "Sent from EMCargo by {sender}.",
    },
    "de": {
        "subject": "Beförderungspapiere {reference}",
        "heading": "Beförderungspapiere",
        "intro": "Im Anhang finden Sie die Beförderungspapiere dieser Sendung.",
        "sender": "Gesendet aus EMCargo von {sender}.",
    },
    "fr": {
        "subject": "Documents de transport {reference}",
        "heading": "Documents de transport",
        "intro": "Les documents de transport de cet envoi sont en pièce jointe.",
        "sender": "Envoyé depuis EMCargo par {sender}.",
    },
}


class Message:
    """One message in both forms, ready to hand to the mail service."""

    __slots__ = ("subject", "text", "html")

    def __init__(self, subject: str, text: str, html: str):
        self.subject, self.text, self.html = subject, text, html


def reset_message(language: str, username: str, link: str, minutes: int) -> Message:
    lang = normalise(language)
    t = RESET[lang]
    intro = t["intro"].format(username=username)
    validity = t["validity"].format(minutes=minutes)
    return Message(
        subject=t["subject"],
        text=_text([intro, validity], link=link, footer=t["ignore"]),
        html=layout(lang, t["heading"], [escape(intro), escape(validity)],
                    button=(escape(t["action"]), link),
                    footer=escape(t["ignore"])),
    )


def invite_message(language: str, username: str, link: str, days: int) -> Message:
    lang = normalise(language)
    t = INVITE[lang]
    validity = t["validity"].format(days=days)
    return Message(
        subject=t["subject"],
        text=_text([t["intro"], t["username_text"].format(username=username),
                    validity], link=link, footer=t["expired"]),
        html=layout(lang, t["heading"],
                    [escape(t["intro"]),
                     t["username"].format(username=escape(username)),
                     escape(validity)],
                    button=(escape(t["action"]), link),
                    footer=escape(t["expired"])),
    )


def sign_in_code_message(language: str, code: str, minutes: int) -> Message:
    lang = normalise(language)
    t = SIGN_IN_CODE[lang]
    validity = t["validity"].format(minutes=minutes)
    return Message(
        subject=t["subject"],
        # The hint is HTML only. It describes holding a finger on a rendered
        # block; in the plain-text fallback there is no block to hold, and an
        # instruction that does not apply is worse than none.
        text=_text([t["intro"], validity], block=code, footer=t["warning"]),
        html=layout(lang, t["heading"], [escape(t["intro"]), escape(validity)],
                    block=escape(code), block_hint=escape(t["hint"]),
                    footer=escape(t["warning"])),
    )


def test_message(language: str) -> Message:
    lang = normalise(language)
    t = TEST[lang]
    return Message(
        subject=t["subject"],
        text=_text([t["intro"], t["explain"]]),
        html=layout(lang, t["heading"], [escape(t["intro"]), escape(t["explain"])]),
    )


def documents_message(language: str, sender: str, reference: str,
                      note: str = "") -> Message:
    """The covering letter for a consignment's papers.

    ``note`` is what the sender typed. It replaces the standard sentence
    rather than joining it: somebody who writes their own message means it
    to be the message.
    """
    lang = normalise(language)
    t = DOCUMENTS[lang]
    body = note.strip() or t["intro"]
    signature = t["sender"].format(sender=sender)
    return Message(
        subject=t["subject"].format(reference=reference).strip(),
        text=_text([body], footer=signature),
        html=layout(lang, t["heading"],
                    [escape(line) for line in body.split("\n") if line.strip()],
                    footer=escape(signature)),
    )
