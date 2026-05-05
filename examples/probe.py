"""Probe SDK responses for the hospital-corridor brief from the README."""

import json
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


# -- 1. Naive single search (the lazy approach) -------------------------------
section("1. NAIVE single-shot search of the full brief")
brief = (
    "High-traffic hospital corridor that needs to meet infection control "
    "standards, LEED Silver minimum, and a calming aesthetic. Budget is mid-range."
)
naive = client.search(brief, limit=8)
print(f"total_results={naive.total_results}, returned={len(naive.results)}")
for r in naive.results:
    print(f"  {r.similarity_score:.2f}  {r.manufacturer_product_name:40} | {r.supplier_name}")


# -- 2. Decomposed product searches ------------------------------------------
section("2. DECOMPOSED product searches (multiple targeted queries)")
queries = [
    "antimicrobial flooring hospital corridor",
    "resilient flooring high traffic healthcare",
    "wall protection healthcare corridor",
    "acoustic ceiling tile healthcare",
    "calming biophilic wall panel",
]
for q in queries:
    res = client.search(q, limit=3)
    print(f"\n  query: {q!r}")
    for r in res.results:
        print(f"    {r.similarity_score:.2f}  {r.manufacturer_product_name:40} | {r.supplier_name}")


# -- 3. Materials with full payload to see `notes` field ---------------------
section("3. MATERIALS - full payload to inspect richness")
mats = client.materials.search("antimicrobial resilient flooring", limit=5)
for m in mats.results:
    print(json.dumps(m.model_dump(), indent=2))


# -- 4. Certifications with descriptions -------------------------------------
section("4. CERTIFICATIONS for 'LEED Silver' and 'infection control'")
for q in ["LEED Silver", "infection control antimicrobial", "low VOC indoor air quality"]:
    print(f"\n  query: {q!r}")
    certs = client.certifications.search(q, limit=3)
    for c in certs.results:
        desc = (c.description or "")[:120].replace("\n", " ")
        print(f"    {c.similarity_score:.2f}  {c.name} | issuer={c.issuing_body_names}")
        if desc:
            print(f"          desc: {desc}...")


# -- 5. Taxonomy classification ----------------------------------------------
section("5. TAXONOMY classification")
tax = client.taxonomy.search(
    product_category_scraped="resilient flooring",
    product_description="Sheet vinyl for hospital corridor with welded seams for infection control",
)
print(f"  new_taxonomy.match_status: {tax.new_taxonomy.match_status}")
if tax.new_taxonomy.matched_taxonomy:
    m = tax.new_taxonomy.matched_taxonomy
    print(f"  matched: {m.display_name} ({m.masterformat_code}) score={m.similarity_score:.2f}")
print(f"  top candidates:")
for c in tax.new_taxonomy.top_candidates[:5]:
    print(f"    {c.similarity_score:.2f} {c.display_name} ({c.masterformat_code})")


# -- 6. Companies known for healthcare ---------------------------------------
section("6. COMPANIES - healthcare flooring manufacturers")
cos = client.companies.search("healthcare flooring manufacturer", limit=5)
for co in cos.results:
    print(f"  {co.similarity_score:.2f}  {co.name:35} | {co.website}")
