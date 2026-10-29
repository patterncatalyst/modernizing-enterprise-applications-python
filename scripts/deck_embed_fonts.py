#!/usr/bin/env python3
"""Embed the fonts actually used in a .pptx deck, in place, via a headless
LibreOffice instance driven over UNO.

Run with the SYSTEM python3 (needs the `uno` bindings that ship with
LibreOffice) -- NOT the project's .venv-decks interpreter:

    python3 scripts/deck_embed_fonts.py DECK.pptx [DECK2.pptx ...]

What it does, per deck:
    1. Launches (once, shared across all decks passed on the command line) a
       headless soffice listener on 127.0.0.1:2002 with a scratch
       UserInstallation profile, so it never touches a real LibreOffice user
       profile and can run alongside an interactive LibreOffice session.
    2. Connects via the UNO bridge.
    3. Loads the deck hidden, flips on the document's font-embedding
       settings (EmbedFonts / EmbedOnlyUsedFonts / EmbedLatinScriptFonts),
       and re-saves it in place with the "Impress MS PowerPoint 2007 XML"
       filter -- same filter name LibreOffice itself uses for .pptx.
    4. Closes the document.
    5. Terminates the soffice listener once all decks are done.

This reproduces exactly what "File > Save As, with font embedding on" does
in the LibreOffice Impress GUI: the fonts come out as ppt/fonts/*.fntdata in
EOT (Embedded OpenType) format, with embedTrueTypeFonts="1" and a
<p:embeddedFontLst> written into ppt/presentation.xml.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

HOST = "127.0.0.1"
PORT = "2002"


def wait_for_socket(host: str, port: str, timeout: float = 60.0) -> None:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"soffice did not open {host}:{port} within {timeout}s")


def start_soffice(profile_dir: str) -> subprocess.Popen:
    accept = f"socket,host={HOST},port={PORT};urp;"
    cmd = [
        "soffice",
        "--headless",
        "--invisible",
        "--nodefault",
        "--norestore",
        "--nologo",
        "--nofirststartwizard",
        f"-env:UserInstallation=file://{profile_dir}",
        f"--accept={accept}",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wait_for_socket(HOST, PORT)
    # Give the UNO service a moment to finish registering after the socket
    # accepts connections -- the first resolve can otherwise race it.
    time.sleep(2.0)
    return proc


def connect(resolver_retries: int = 10):
    import uno
    from com.sun.star.connection import NoConnectException

    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_ctx
    )
    url = f"uno:socket,host={HOST},port={PORT};urp;StarOffice.ComponentContext"
    last_exc = None
    for _ in range(resolver_retries):
        try:
            ctx = resolver.resolve(url)
            return ctx
        except NoConnectException as exc:
            last_exc = exc
            time.sleep(1.0)
    raise RuntimeError(f"could not connect to soffice listener: {last_exc}")


def embed_fonts_in_deck(ctx, path: str) -> None:
    import uno
    from com.sun.star.beans import PropertyValue

    def mkprop(name, value):
        p = PropertyValue()
        p.Name = name
        p.Value = value
        return p

    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)

    abs_path = os.path.abspath(path)
    load_url = uno.systemPathToFileUrl(abs_path)

    load_props = (
        mkprop("Hidden", True),
        mkprop("UpdateDocMode", 1),  # NO_UPDATE
    )
    doc = desktop.loadComponentFromURL(load_url, "_blank", 0, load_props)
    if doc is None:
        raise RuntimeError(f"failed to load {path}")

    try:
        settings = doc.createInstance("com.sun.star.document.Settings")
        settings.EmbedFonts = True
        for optional_prop, value in (
            ("EmbedOnlyUsedFonts", True),
            ("EmbedLatinScriptFonts", True),
            ("EmbedAsianScriptFonts", False),
            ("EmbedComplexScriptFonts", False),
        ):
            try:
                setattr(settings, optional_prop, value)
            except Exception:
                pass  # property not present on this LO version -- fine, skip it

        store_props = (mkprop("FilterName", "Impress MS PowerPoint 2007 XML"),)
        doc.storeToURL(load_url, store_props)
    finally:
        doc.close(False)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1

    profile_dir = tempfile.mkdtemp(prefix="deck-embed-fonts-profile-")
    proc = start_soffice(profile_dir)
    try:
        ctx = connect()
        for deck in argv:
            print(f"embedding fonts: {deck}")
            embed_fonts_in_deck(ctx, deck)
            print(f"  done: {deck}")
        return 0
    finally:
        try:
            ctx_smgr = ctx.ServiceManager  # noqa: F841
            desktop = ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", ctx
            )
            desktop.terminate()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
