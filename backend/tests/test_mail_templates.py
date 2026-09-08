"""What outgoing mail says, and what it must not say.

Three properties, each of which the messages shipped without at first:

1. **The reader's language, not the sender's.** A colleague whose EMCargo
   is in German got an English invitation, because the wording lived in the
   code as one English string.
2. **A letter, not a wall of text** — and one that arrives intact, with the
   logo carried along rather than fetched from this server.
3. **No administrator's user name in an invitation.** "admin has made an
   account for you" tells its reader which account is an administrator's,
   including readers who should never have learnt that.
"""
import pytest

from app.core.languages import SUPPORTED
from app.schemas.settings import InstanceSettings
from app.services import mail, mail_templates


def configured() -> InstanceSettings:
    return InstanceSettings(mail_enabled=True, mail_host="smtp.example.com",
                            mail_from="emcargo@example.com")


ALL_BUILDERS = [
    lambda lang: mail_templates.reset_message(lang, "ada", "https://x/y", 60),
    lambda lang: mail_templates.invite_message(lang, "ada", "https://x/y", 7),
    lambda lang: mail_templates.sign_in_code_message(lang, "123456", 5),
    lambda lang: mail_templates.test_message(lang),
    lambda lang: mail_templates.documents_message(lang, "ada", "CP-1"),
]


# --- the language -----------------------------------------------------------


@pytest.mark.parametrize("language", SUPPORTED)
@pytest.mark.parametrize("build", ALL_BUILDERS)
def test_every_message_exists_in_every_language(build, language):
    message = build(language)
    assert message.subject and message.text and message.html
    assert f'lang="{language}"' in message.html


def test_the_dutch_reset_is_dutch_and_the_german_one_german():
    nl = mail_templates.reset_message("nl", "ada", "https://x/y", 60)
    de = mail_templates.reset_message("de", "ada", "https://x/y", 60)
    assert nl.subject == "Wachtwoord opnieuw instellen"
    assert "wachtwoord" in nl.text.lower()
    # The call to action lives on the button, which is the HTML's own.
    assert "Kies een nieuw wachtwoord" in nl.html
    assert de.subject == "Passwort zurücksetzen"
    assert "Passwort" in de.text


def test_an_unknown_language_falls_back_rather_than_failing():
    """A stored preference for a language that was dropped must not stop
    somebody from resetting their password."""
    message = mail_templates.reset_message("kl", "ada", "https://x/y", 60)
    assert message.subject == mail_templates.RESET["nl"]["subject"]


# --- what the invitation gives away -----------------------------------------


@pytest.mark.parametrize("language", SUPPORTED)
def test_the_invitation_never_names_the_administrator(language):
    """It used to read "admin has made an account for you", which hands an
    administrator's user name to whoever opens the message."""
    message = mail_templates.invite_message(language, "nieuwe-collega",
                                            "https://x/y", 7)
    # The body says who made the account only by role. (The subject names
    # neither, which is right: it is about the reader's own account.)
    for body in (message.text, message.html):
        assert any(word in body.lower() for word in
                   ("beheerder", "administrator", "administrateur"))
    # The reader's own name belongs there; nobody else's does.
    assert "nieuwe-collega" in message.text


def test_the_invitation_carries_the_link_and_its_lifetime():
    message = mail_templates.invite_message("nl", "ada", "https://cp/x?token=abc", 7)
    assert "https://cp/x?token=abc" in message.text
    assert "https://cp/x?token=abc" in message.html
    assert "7 dagen" in message.text


# --- the shape of the letter ------------------------------------------------


def test_a_message_is_plain_text_and_html_and_carries_its_logo():
    message = mail_templates.test_message("nl")
    built = mail.build_message(configured(), "ada@example.com",
                               message.subject, message.text, html=message.html)
    types = [part.get_content_type() for part in built.walk()]
    assert "text/plain" in types
    assert "text/html" in types
    assert "image/png" in types


def test_the_logo_travels_with_the_message_rather_than_being_fetched():
    """A linked image makes the reader's client call this server: a tracking
    pixel by accident, and a broken image on an installation the internet
    cannot reach."""
    message = mail_templates.test_message("nl")
    assert f'src="cid:{mail_templates.LOGO_CID}"' in message.html
    assert "http://" not in message.html.replace("http://www.w3.org", "")

    built = mail.build_message(configured(), "ada@example.com",
                               message.subject, message.text, html=message.html)
    images = [p for p in built.walk() if p.get_content_type() == "image/png"]
    assert images and images[0].get("Content-ID") == f"<{mail_templates.LOGO_CID}>"


def test_a_message_without_html_stays_a_plain_one():
    built = mail.build_message(configured(), "ada@example.com", "S", "Body")
    assert built.get_content_type() == "text/plain"


def test_the_plain_text_says_the_same_as_the_html():
    """The text is not a leftover: somebody reading it must learn the same
    things, including the code and the link."""
    code = mail_templates.sign_in_code_message("nl", "654321", 5)
    assert "654321" in code.text and "654321" in code.html

    reset = mail_templates.reset_message("nl", "ada", "https://cp/reset?t=1", 60)
    assert "https://cp/reset?t=1" in reset.text
    assert "60 minuten" in reset.text and "60 minuten" in reset.html


def test_a_user_name_with_html_in_it_cannot_break_out():
    """User names are not markup, and a mail client is a renderer."""
    message = mail_templates.invite_message(
        "nl", "<script>alert(1)</script>", "https://x/y", 7)
    assert "<script>" not in message.html
    assert "&lt;script&gt;" in message.html


def test_the_senders_own_words_replace_the_standard_sentence():
    """Somebody who writes their own covering note means it to be the note,
    not a preface to a canned one."""
    written = mail_templates.documents_message(
        "nl", "ada", "CP-1", note="Beste Jan, hierbij de papieren.")
    assert "Beste Jan" in written.text
    assert mail_templates.DOCUMENTS["nl"]["intro"] not in written.text
    # And the sender is still named, because the reader has to know who sent it.
    assert "ada" in written.text


def test_the_document_subject_carries_the_reference():
    message = mail_templates.documents_message("nl", "ada", "CP-2026-100")
    assert "CP-2026-100" in message.subject


# --- what makes it fit on a phone -------------------------------------------
#
# The invitation arrived on an Android phone hanging off the right of the
# screen. None of these four is visible in a desktop preview, which is why
# they are pinned here rather than looked at.


@pytest.mark.parametrize("build", ALL_BUILDERS)
def test_every_message_tells_the_phone_how_wide_it_is(build):
    """The one that actually mattered.

    Without this line a client lays the message out in a desktop-width
    container and shows the phone a slice. Measured in a 980-pixel
    container, the card is centred starting at x=210 — a wide margin on the
    left, the card running off the right — which is what an invitation
    looked like on the phone that reported it.
    """
    html = build("nl").html
    assert '<meta name="viewport" content="width=device-width,initial-scale=1" />' in html


def test_the_gutter_is_a_table_cell_rather_than_body_padding():
    """Gmail lifts the content into its own container and drops body styles.
    Padding on <body> is therefore honoured in some clients and not in
    others — the same message, two different layouts."""
    html = mail_templates.test_message("nl").html
    assert "<body style=\"margin:0;padding:0;" in html
    assert 'align="center" style="padding:16px;"' in html


def test_the_card_is_centred_the_way_word_understands():
    """Outlook renders with Word, which ignores margin:0 auto."""
    html = mail_templates.test_message("nl").html
    assert "margin:0 auto" not in html
    assert html.count('align="center"') >= 2
    assert "max-width:560px" in html


def test_a_long_link_may_break_anywhere():
    """An unbroken 60-character token sets a minimum width for the whole
    table, and a table wider than the screen is exactly what pushed the
    message off to the right. No single wrapping rule is honoured by every
    client, so all three are given."""
    long_link = ("https://emcargo.example.nl/reset-password?token="
                 "lTQayKEQt0IqTAxhxtSbKPaK4gB87E2_mHj_HlT29Jg")
    html = mail_templates.invite_message("nl", "berry", long_link, 7).html
    assert long_link in html
    for rule in ("word-break:break-all", "overflow-wrap:anywhere",
                 "word-wrap:break-word"):
        assert rule in html


@pytest.mark.parametrize("build", ALL_BUILDERS)
def test_nothing_is_wider_than_a_narrow_phone(build):
    """A fixed pixel width beyond a small screen is the other way a message
    ends up sideways. 320 is the narrowest phone still in use."""
    import re

    html = build("nl").html
    # Percentages and max-width are the safe forms and are meant to be here;
    # a *fixed* width beyond a small screen is the one that hurts.
    fixed = [int(w) for w in re.findall(r"(?<!max-)width:(\d+)px", html)]
    fixed += [int(w) for w in re.findall(r'width="(\d+)"(?!%)', html)]
    assert all(width <= 320 for width in fixed), fixed


# --- the copy glyph beside a sign-in code -----------------------------------


def test_the_code_carries_the_copy_glyph_and_says_what_to_do_with_it():
    """A mail client has no clipboard API and no JavaScript, so nothing here
    can copy on a tap. What does put the code on the clipboard is the reader
    holding a finger on it, so the glyph is a cue and the sentence beside it
    is the instruction — a glyph on its own would promise a button."""
    message = mail_templates.sign_in_code_message("nl", "472302", 5)
    assert f'src="cid:{mail_templates.COPY_ICON_CID}"' in message.html
    assert "ingedrukt" in message.html


@pytest.mark.parametrize("language", ["nl", "en", "de", "fr"])
def test_the_instruction_speaks_every_language(language):
    message = mail_templates.sign_in_code_message(language, "472302", 5)
    assert mail_templates.SIGN_IN_CODE[language]["hint"] in message.html


def test_the_glyph_travels_with_the_message_like_the_logo():
    message = mail_templates.sign_in_code_message("nl", "472302", 5)
    built = mail.build_message(configured(), "ada@example.com",
                               message.subject, message.text, html=message.html)
    cids = {p.get("Content-ID") for p in built.walk()
            if p.get_content_type() == "image/png"}
    assert f"<{mail_templates.LOGO_CID}>" in cids
    assert f"<{mail_templates.COPY_ICON_CID}>" in cids


def test_a_message_without_a_code_does_not_haul_the_glyph():
    """The guard that keeps an invitation from carrying an icon it never
    shows — the same one the logo has, for the same reason."""
    message = mail_templates.invite_message("nl", "ada", "https://cp/i?t=1", 7)
    assert mail_templates.COPY_ICON_CID not in message.html

    built = mail.build_message(configured(), "ada@example.com",
                               message.subject, message.text, html=message.html)
    cids = {p.get("Content-ID") for p in built.walk()
            if p.get_content_type() == "image/png"}
    assert f"<{mail_templates.COPY_ICON_CID}>" not in cids


def test_the_press_selects_the_code_and_not_the_glyph():
    """The glyph sits in its own table cell, never inside the code's.

    Inside it, a long press would sweep the image into the selection and the
    reader would paste six digits and a picture. This is the whole reason the
    block is a table rather than one padded paragraph.
    """
    html = mail_templates.sign_in_code_message("nl", "472302", 5).html
    code_cell = html.split("472302")[0].rsplit("<td", 1)[-1]
    assert "<img" not in code_cell


def test_the_glyph_is_the_applications_own_drawing():
    """No third-party licence travels into the mail.

    docs/data-sources.md records that the copy, delete, pencil and chevron
    glyphs are hand-written paths in this repository, and the mail renders
    from those same paths — so the eight credited Uicons icons stay eight.
    """
    import pathlib
    import re

    # Read as text rather than imported: scripts/ is beside the backend, not
    # inside it, and this assertion is about two files agreeing — which is a
    # question about their contents, not about importability.
    repo = pathlib.Path(__file__).resolve().parents[2]
    script = (repo / "scripts" / "render_mail_icons.py").read_text(encoding="utf-8")
    component = (repo / "frontend" / "src" / "components"
                 / "ReviewLinesPanel.tsx").read_text(encoding="utf-8")

    paths = re.findall(r'd="(M[^"]+)"', script)
    assert paths, "the script no longer carries the glyph's paths"
    for path in paths:
        assert path in component, path
