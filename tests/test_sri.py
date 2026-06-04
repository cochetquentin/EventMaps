"""Tests vérifiant la présence des hashes SRI dans frontend/index.html (SEC-003)."""
import re
from pathlib import Path

HTML = Path("frontend/index.html").read_text(encoding="utf-8")

EXPECTED_SRI = {
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css": (
        "sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H"
    ),
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js": (
        "sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH"
    ),
    "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css": (
        "sha384-pmjIAcz2bAn0xukfxADbZIb3t8oRT9Sv0rvO+BR5Csr6Dhqq+nZs59P0pPKQJkEV"
    ),
    "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css": (
        "sha384-wgw+aLYNQ7dlhK47ZPK7FRACiq7ROZwgFNg0m04avm4CaXS+Z9Y7nMu8yNjBKYC+"
    ),
    "https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js": (
        "sha384-eXVCORTRlv4FUUgS/xmOyr66XBVraen8ATNLMESp92FKXLAMiKkerixTiBvXriZr"
    ),
}


def test_sri_hashes_present():
    """Chaque URL CDN doit avoir son hash SRI attendu dans le HTML."""
    for url, expected_hash in EXPECTED_SRI.items():
        assert url in HTML, f"URL CDN absente du HTML : {url}"
        assert expected_hash in HTML, (
            f"Hash SRI manquant ou incorrect pour {url}\n"
            f"Attendu : {expected_hash}"
        )


def test_crossorigin_present_for_unpkg_resources():
    """Toute ressource unpkg.com doit avoir crossorigin=\"anonymous\"."""
    tag_pattern = re.compile(r"<(?:link|script)[^>]+unpkg\.com[^>]+>", re.DOTALL)
    tags = tag_pattern.findall(HTML)
    assert len(tags) == 5, f"Attendu 5 balises unpkg, trouvé {len(tags)}"
    for tag in tags:
        assert 'crossorigin="anonymous"' in tag, (
            f"crossorigin manquant sur la balise : {tag[:120]}"
        )


def test_integrity_attribute_format():
    """Les attributs integrity doivent suivre le format sha384-<base64>."""
    integrity_pattern = re.compile(r'integrity="(sha384-[A-Za-z0-9+/]+=*)"')
    found = integrity_pattern.findall(HTML)
    assert len(found) == 5, (
        f"Attendu 5 attributs integrity sha384, trouvé {len(found)}"
    )
