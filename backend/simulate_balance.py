import sys

sys.path.insert(0, r"c:\Users\natbo\Documents\buildandburn\brain\backend")

import asyncio

from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models import Node
from src.services.solver import CoherenceSolverService

# Mapping texts to user_import names for readability
TEXT_TO_NAME = {
    "Aucun agent n'est l'origine ultime de son propre caractère": "d1 (origine_ultime_neg)",
    "Le caractère, les capacités et l'effort d'une personne": "d2 (caractere_environnement)",
    "Les différences de maîtrise de soi et de volonté": "d3 (neurobio_volonte)",
    "Le mérite de base exige que l'agent soit l'origine ultime": "b1 (merite_exige_source)",
    "Personne ne mérite de base ses récompenses ni ses peines": "c1 (merite_neg)",
    "Traiter quelqu'un comme méritant une récompense ou une peine": "b2 (injuste_non_merite)",
    "La justice rétributive (punir parce que c'est mérité)": "c2 (retributive_injuste)",
    "La méritocratie n'est pas justifiée par le desert": "c3 (meritocratie_injuste)",
    "Les institutions doivent se justifier de façon prospective": "pos1 (prospective_justif)",
    "La responsabilité morale n'exige pas d'origination ultime": "b3 (moral_respons_compat)",
    "Un agent peut mériter éloge ou blâme s'il agit à partir": "pos2 (eloge_blame_compat)",
    "Les attitudes réactives (gratitude, ressentiment)": "b4 (attitudes_reactives)",
    "Une forme de mérite résiste au déterminisme": "c4 (merite_compat)",
}


def get_name(node):
    for key, name in TEXT_TO_NAME.items():
        if key in node.text:
            return name
    return node.text[:30]


async def run_simulation():
    async with AsyncSessionLocal() as session:
        # Load nodes
        nodes_res = await session.execute(select(Node))
        nodes = nodes_res.scalars().all()

        print(f"Loaded {len(nodes)} nodes from DB.")

        # 1. Run baseline
        baseline = await CoherenceSolverService.solve(session)
        print("\n--- BASELINE SOLVER RESULT ---")
        print(
            f"Score: {baseline['score']}, Incoherence: {baseline['incoherence_score']}"
        )
        print("Accepted:")
        for nid in baseline["accepted"]:
            node = next(n for n in nodes if n.id == nid)
            print(f"  + {get_name(node)} (Tier: {node.tier}, Weight: {node.weight})")
        print("Rejected:")
        for nid in baseline["rejected"]:
            node = next(n for n in nodes if n.id == nid)
            print(f"  - {get_name(node)} (Tier: {node.tier}, Weight: {node.weight})")

        # 2. Run equalized simulation
        # Equalize all critical debate nodes: b1, b3, b4, c1, c4
        # We will override their tiers to 'moyen'
        tier_overrides = {}
        for n in nodes:
            name = get_name(n)
            if any(
                name.startswith(prefix) for prefix in ["b1", "b3", "b4", "c1", "c4"]
            ):
                tier_overrides[n.id] = "moyen"

        # Run solver with overrides
        equalized = await CoherenceSolverService.solve(
            session, tier_overrides=tier_overrides
        )
        print("\n--- EQUALIZED SOLVER RESULT ---")
        print(
            f"Score: {equalized['score']}, Incoherence: {equalized['incoherence_score']}"
        )
        print("Accepted:")
        for nid in equalized["accepted"]:
            node = next(n for n in nodes if n.id == nid)
            print(
                f"  + {get_name(node)} (New Tier: {tier_overrides.get(node.id, node.tier)})"
            )
        print("Rejected:")
        for nid in equalized["rejected"]:
            node = next(n for n in nodes if n.id == nid)
            print(
                f"  - {get_name(node)} (New Tier: {tier_overrides.get(node.id, node.tier)})"
            )

        # 3. Tipping the balance: make c4 slightly stronger ('fort')
        tipping_overrides = dict(tier_overrides)
        for n in nodes:
            name = get_name(n)
            if name.startswith("c4"):
                tipping_overrides[n.id] = "fort"
                print(f"Tipping balance: Overriding {name} to TIER=fort")

        tipping = await CoherenceSolverService.solve(
            session, tier_overrides=tipping_overrides
        )
        print("\n--- TIPPED SOLVER RESULT (c4 = fort) ---")
        print(f"Score: {tipping['score']}, Incoherence: {tipping['incoherence_score']}")
        print("Accepted:")
        for nid in tipping["accepted"]:
            node = next(n for n in nodes if n.id == nid)
            print(
                f"  + {get_name(node)} (Tipped Tier: {tipping_overrides.get(node.id, node.tier)})"
            )
        print("Rejected:")
        for nid in tipping["rejected"]:
            node = next(n for n in nodes if n.id == nid)
            print(
                f"  - {get_name(node)} (Tipped Tier: {tipping_overrides.get(node.id, node.tier)})"
            )


if __name__ == "__main__":
    asyncio.run(run_simulation())
