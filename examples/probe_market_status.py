"""Probe what `market_status` and `status_name` strings the SDK actually returns.

Stage 4's rank prompt cites the literal example `"Live on Acelab"`. This script
verifies whether that string actually appears in real responses, and surfaces
the full set of distinct values so the prompt can be grounded in reality
instead of an assumption.
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter

from dotenv import load_dotenv

from acelab import AsyncAcelab

load_dotenv()

QUERIES = [
    "high-traffic hospital corridor flooring infection control",
    "LEED Silver low VOC carpet tile commercial",
    "biophilic acoustic ceiling tile",
    "school cafeteria slip-resistant resilient flooring",
    "luxury residential kitchen countertop",
    "wall protection healthcare antimicrobial",
    "Mannington commercial flooring",
    "modern industrial concrete sealer",
    "FSC certified wood paneling",
    "GREENGUARD Gold ceiling tile",
]


async def main() -> None:
    api_key = os.environ["ACELAB_API_KEY"]
    base_url = os.environ["ACELAB_BASE_URL"]

    product_market_status: Counter[str] = Counter()
    product_status_name: Counter[str] = Counter()
    company_status_name: Counter[str] = Counter()
    company_market_status: Counter[str] = Counter()

    total_products = 0
    total_companies = 0

    async with AsyncAcelab(api_key=api_key, base_url=base_url) as client:
        for q in QUERIES:
            res = await client.search(q, limit=8)
            for r in res.results:
                total_products += 1
                product_market_status[repr(r.market_status)] += 1
                product_status_name[repr(r.status_name)] += 1

        for c_query in ["Mannington", "Interface", "Armstrong", "Shaw"]:
            cres = await client.companies.search(c_query, limit=5)
            for r in cres.results:
                total_companies += 1
                company_status_name[repr(r.status_name)] += 1
                company_market_status[repr(r.market_status)] += 1

    print(f"Products sampled: {total_products}")
    print("Distinct ProductSearchResult.market_status values:")
    for v, n in product_market_status.most_common():
        print(f"  {n:4d}  {v}")
    print("Distinct ProductSearchResult.status_name values:")
    for v, n in product_status_name.most_common():
        print(f"  {n:4d}  {v}")

    print(f"\nCompanies sampled: {total_companies}")
    print("Distinct CompanySearchResult.status_name values:")
    for v, n in company_status_name.most_common():
        print(f"  {n:4d}  {v}")
    print("Distinct CompanySearchResult.market_status values:")
    for v, n in company_market_status.most_common():
        print(f"  {n:4d}  {v}")


if __name__ == "__main__":
    asyncio.run(main())
