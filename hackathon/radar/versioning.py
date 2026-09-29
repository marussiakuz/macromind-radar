"""A saved pool is reusable only under the pipeline and limits that produced it."""
import hashlib
import json

POOL_VERSION = "pool/2026-09-29-recall1"


def pool_signature(settings, plan="tree", lenses=("product", "funding", "standard", "research")):
    from .discovery import VERSION as discovery_version
    from .extract import PROMPT_VERSION
    from .selection import VERSION as selection_version
    payload = {"version": POOL_VERSION, "plan": plan, "discovery": discovery_version,
               "selection": selection_version, "extraction": PROMPT_VERSION,
               "model": settings.model_uri, "limits": settings.limits.__dict__,
               "lenses": "tree_schedule" if plan == "tree" else list(lenses)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
