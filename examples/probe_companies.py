"""Re-probe companies endpoint - it's name-based, not description-based."""

import os

from dotenv import load_dotenv

load_dotenv()

from acelab import Acelab

client = Acelab(
    api_key=os.getenv("ACELAB_API_KEY"),
    base_url=os.getenv("ACELAB_BASE_URL"),
)


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# -- A. Lookup by brand names that surfaced in product search ----------------
section("A. Brand-name lookup (suppliers from product hits)")
suppliers = [
    "Armstrong Flooring",
    "Gerflor",
    "Mannington Commercial",
    "Shaw",
    "Stonhard",
    "Yeoman Shield",
    "Inpro",
]
for s in suppliers:
    res = client.companies.search(s, limit=3)
    print(f"\n  query: {s!r}")
    for co in res.results:
        print(f"    {co.similarity_score:.2f}  {co.name:35} | status={co.status_name} | {co.website}")


# -- B. Brief-mentioned brand (a user might name-drop a manufacturer) -------
section("B. Brief mentions a brand directly")
for q in ["Forbo Marmoleum", "Tarkett healthcare", "Interface carpet tile"]:
    res = client.companies.search(q, limit=3)
    print(f"\n  query: {q!r}")
    for co in res.results:
        print(f"    {co.similarity_score:.2f}  {co.name:35} | status={co.status_name}")


# -- C. Cross-reference: does the company have related products? ------------
section("C. Round-trip: find brand, then search products from that brand")
res = client.companies.search("Mannington Commercial", limit=1)
if res.results:
    co = res.results[0]
    print(f"  Found company: {co.name} ({co.long_name}) | website={co.website}")
    # Now search products mentioning this brand
    prods = client.search(f"{co.name} healthcare flooring", limit=5)
    print(f"\n  Products from this brand for healthcare:")
    for p in prods.results:
        print(f"    {p.similarity_score:.2f}  {p.manufacturer_product_name:35} | {p.supplier_name}")
