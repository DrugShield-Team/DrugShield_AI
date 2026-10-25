"""
DrugShield AI - UPI Resolver & Triangulation Service
====================================================
Cross-references parsed UPI addresses against NPCI banking handles,
synthetic mule accounts, and triangulates financial flows.
"""

from typing import Dict, Any, List
from src.osint_triangulation.upi_parser import extract_financial_entities, parse_upi_uri

class UPIResolver:
    """Resolves and triangulates UPI VPAs to financial institutions and risk tiers."""
    
    def __init__(self):
        self.known_flagged_vpas = {
            "dealer_blr@okhdfcbank": {"risk": "HIGH", "category": "Narcotics Distributor"},
            "dark_supply@paytm": {"risk": "HIGH", "category": "Payment Aggregator Mule"},
            "syndicate_score@ybl": {"risk": "CRITICAL", "category": "Cartel Node"}
        }

    def resolve_vpa(self, vpa: str) -> Dict[str, Any]:
        """Resolves a single UPI VPA against known risk databases."""
        clean_vpa = vpa.strip().lower()
        handle = clean_vpa.split("@")[-1] if "@" in clean_vpa else "unknown"
        
        flagged_entry = self.known_flagged_vpas.get(clean_vpa)
        return {
            "vpa": clean_vpa,
            "bank_handle": handle,
            "is_flagged": bool(flagged_entry),
            "intelligence": flagged_entry or {"risk": "UNKNOWN", "category": "Unindexed"}
        }

    def triangulate_text(self, text: str) -> Dict[str, Any]:
        """Full triangulation scan of message content."""
        entities = extract_financial_entities(text)
        resolved_vpas = [self.resolve_vpa(v) for v in entities.get("upi_ids", [])]
        return {
            **entities,
            "resolved_vpas": resolved_vpas
        }

# Module entry point
resolver = UPIResolver()
triangulate_text = resolver.triangulate_text
