#!/usr/bin/env python3
"""Optional real-browser privacy workflow proof; synthetic fixture only."""
import argparse
import csv
import io
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from star_wpa.privacy import OUTPUT_HEADER, parse_source
from star_wpa.privacy_ui import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", help="optional synthetic-only screenshot path")
    parser.add_argument("--browser", help="optional installed Chromium executable")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright, expect

    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/privacy-wigle.csv"
    original = fixture.read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "sanitized.csv"
        with make_server(parse_source(original, "wigle"), output) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=args.browser)
                    context = browser.new_context(viewport={"width": 1200, "height": 1200})
                    page = context.new_page()
                    errors, destinations = [], []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("request", lambda request: destinations.append(request.url))
                    base = f"http://127.0.0.1:{server.server_port}"
                    page.goto(base + "/")
                    assert page.locator("#export").is_disabled()
                    page.locator("#preview").click()
                    expect(page.locator("#status")).to_contain_text("3 unique output rows")
                    assert not output.exists()
                    for field, value in {"south": "10", "west": "20", "north": "10.6", "east": "20.6", "buffer_m": "100"}.items():
                        page.locator("#" + field).fill(value)
                    page.get_by_role("button", name="Add exclusion").click()
                    assert page.locator("#export").is_disabled()
                    page.locator("#preview").click()
                    expect(page.locator("#status")).to_contain_text("2 excluded; 1 unique output rows")
                    # A coarse-only point can shift well outside source-only bounds.
                    page.locator("#precision").select_option("0")
                    assert page.locator("#export").is_disabled()
                    page.locator("#preview").click()
                    expect(page.locator("#export")).to_be_enabled()
                    if args.screenshot:
                        page.screenshot(path=args.screenshot, full_page=True)
                    page.locator("#export").click()
                    expect(page.locator("#status")).to_contain_text("Saved a new sanitized CSV")
                    records = list(csv.DictReader(io.StringIO(output.read_text())))
                    assert len(records) == 1 and tuple(records[0]) == OUTPUT_HEADER
                    assert records[0]["latitude"] == "11.000000"
                    assert fixture.read_bytes() == original
                    assert b"SYNTHETIC" not in output.read_bytes()
                    assert all(url.startswith(base + "/") for url in destinations), destinations
                    assert not errors, errors
                    assert page.evaluate("localStorage.length + sessionStorage.length") == 0
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    context.close()
                    browser.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
    print("PASS: Chromium offline preview, exclusions, precision, new-copy export, no external requests/storage, source preservation and mobile layout")


if __name__ == "__main__":
    main()
