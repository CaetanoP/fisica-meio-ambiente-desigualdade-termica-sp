import os
from playwright.sync_api import sync_playwright
from pptx import Presentation
from pptx.util import Inches

HTML_FILE = os.path.abspath("slides.html")
OUTPUT_PPTX = "Aula_Expositiva_Desigualdade_Termica_SP.pptx"
OUTPUT_PDF = "Aula_Expositiva_Desigualdade_Termica_SP.pdf"
TEMP_DIR = "_slide_renders"


def build():
    os.makedirs(TEMP_DIR, exist_ok=True)
    png_paths = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        page.goto(f"file://{HTML_FILE}", wait_until="networkidle")

        # Export crisp vector PDF directly from Chromium
        page.pdf(
            path=OUTPUT_PDF,
            width="1280px",
            height="720px",
            print_background=True,
            margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
        )

        slides = page.locator("section.slide")
        count = slides.count()
        for i in range(count):
            out_png = os.path.join(TEMP_DIR, f"slide_{i+1:02d}.png")
            slides.nth(i).screenshot(path=out_png)
            png_paths.append(out_png)

        browser.close()

    # Pack all crisp 2560x1440 (2x Retina) slides into a 16:9 PPTX
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    for png in png_paths:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(png, Inches(0), Inches(0), width=Inches(13.333), height=Inches(7.5))

    prs.save(OUTPUT_PPTX)
    print(f"Generated {OUTPUT_PPTX} and {OUTPUT_PDF} ({len(png_paths)} slides).")


if __name__ == "__main__":
    build()
