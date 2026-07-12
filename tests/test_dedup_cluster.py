"""Tests du clustering et du choix de représentant canonique."""

from datetime import UTC, date, datetime

from dedup.cluster import assign_canonical_ids, canonical_representative
from models.event import Event
from models.identity import make_event_id


def mk(source="tc", **over) -> Event:
    url = over.pop("url", f"https://{source}.example/{over.get('title', 'x')}")
    title = over.pop("title", "Event")
    base = dict(
        id=over.pop("id", None) or make_event_id([url, title, source]),
        source=source,
        title=title,
        url=url,
        start_date=date(2026, 7, 25),
        end_date=None,
        times=None,
        venue=None,
        latitude=None,
        longitude=None,
        price=None,
        attributes=over.pop("attributes", {}),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(over)
    return Event(**base)


def test_singletons_map_to_themselves():
    a = mk("tc", title="Alpha", latitude=35.10, longitude=139.10)
    b = mk("tc", title="Beta", latitude=36.90, longitude=140.90)
    mapping = assign_canonical_ids([a, b])
    assert mapping[a.id] == a.id
    assert mapping[b.id] == b.id


def test_empty_input():
    assert assign_canonical_ids([]) == {}


def test_two_duplicates_share_canonical():
    a = mk("hanabi", title="Sumida Fireworks", latitude=35.711, longitude=139.801)
    b = mk("tc", title="Sumida Fireworks", latitude=35.711, longitude=139.801)
    mapping = assign_canonical_ids([a, b])
    assert mapping[a.id] == mapping[b.id]
    # Le représentant est l'un des deux membres.
    assert mapping[a.id] in {a.id, b.id}


def test_transitive_clustering():
    # A~B et B~C (via lieu proche + titre) → A, B, C dans le même cluster,
    # même si A et C ne sont pas comparés directement de façon évidente.
    a = mk("tc", title="Sumida River Fireworks", latitude=35.7110, longitude=139.8010)
    b = mk("hanabi", title="Sumida River Fireworks", latitude=35.7115, longitude=139.8011)
    c = mk(
        "tot",
        title="Sumida River Fireworks",
        attributes={"venue_name": "Sumida"},
        venue="Sumida",
        latitude=35.7120,
        longitude=139.8012,
    )
    mapping = assign_canonical_ids([a, b, c])
    assert mapping[a.id] == mapping[b.id] == mapping[c.id]


def test_two_independent_clusters():
    a = mk("tc", title="Fireworks A", latitude=35.10, longitude=139.10)
    b = mk("hanabi", title="Fireworks A", latitude=35.10, longitude=139.10)
    c = mk("tc", title="Market B", latitude=36.90, longitude=140.90)
    d = mk(
        "tot",
        title="Market B",
        venue="Central Plaza",
        latitude=36.90,
        longitude=140.90,
        attributes={"venue_name": "Central Plaza"},
    )
    mapping = assign_canonical_ids([a, b, c, d])
    assert mapping[a.id] == mapping[b.id]
    assert mapping[c.id] == mapping[d.id]
    assert mapping[a.id] != mapping[c.id]


def test_duplicate_ids_deduplicated():
    # Deux Event avec le même id (existant + re-scrape) ne cassent pas le clustering.
    a = mk("tc", id="fixedid", title="Alpha", latitude=35.1, longitude=139.1)
    a_bis = mk("tc", id="fixedid", title="Alpha", latitude=35.1, longitude=139.1)
    mapping = assign_canonical_ids([a, a_bis])
    assert mapping == {"fixedid": "fixedid"}


def test_intra_source_dated_variants_collapse_to_one():
    # Cas réel Tokyo Cheapo : un même événement publié en plusieurs pages datées
    # (même slug), dates disjointes → un seul cluster malgré les dates.
    base = "https://tokyocheapo.com/events/geisha-ozashiki-odori-asakusa"
    loc = "Asakusa Culture and Tourism Center"
    variants = [
        mk(
            "tc",
            id="v0",
            title="Free Geisha Dances (Ozashiki Odori) in Asakusa",
            url=f"{base}/",
            start_date=date(2026, 4, 11),
            end_date=date(2026, 7, 11),
            latitude=35.710689,
            longitude=139.79659,
            attributes={"location_name": loc},
        ),
        mk(
            "tc",
            id="v1",
            title="Free Geisha Dances (Ozashiki Odori) in Asakusa",
            url=f"{base}/20260606/",
            start_date=date(2026, 6, 6),
            end_date=date(2026, 9, 5),
            latitude=35.710689,
            longitude=139.79659,
            attributes={"location_name": loc},
        ),
        mk(
            "tc",
            id="v2",
            title="Geisha Dances (Ozashiki Odori) in Asakusa",
            url=f"{base}/20260711/",
            start_date=date(2026, 7, 11),
            end_date=date(2026, 7, 11),
            latitude=35.710689,
            longitude=139.79659,
            attributes={"location_name": loc},
        ),
    ]
    # Un événement voisin au MÊME lieu mais slug différent → doit rester séparé.
    other = mk(
        "tc",
        id="other",
        title="Asakusa Geisha Performance",
        url="https://tokyocheapo.com/events/asakusa-geisha-performance/20260613/",
        start_date=date(2026, 6, 13),
        latitude=35.710689,
        longitude=139.79659,
        attributes={"location_name": loc},
    )
    mapping = assign_canonical_ids([*variants, other])
    assert mapping["v0"] == mapping["v1"] == mapping["v2"]
    assert mapping["other"] == "other"
    assert mapping["other"] != mapping["v0"]


def test_intra_source_multivenue_museums_stay_separate():
    # Cas réel "Summer Night Museums" : même URL, mêmes dates, 4 musées distincts.
    # Deux d'entre eux sont à ~0,6 km (Teien / Photographic) : la géo seule les
    # fusionnerait à tort — le nom de lieu doit les garder séparés → 4 pins.
    url = "https://tokyocheapo.com/events/summer-night-museums/"

    def museum(mid, name, lat, lon):
        return mk(
            "tc",
            id=mid,
            title="Summer Night Museums",
            url=url,
            start_date=date(2026, 6, 7),
            end_date=date(2026, 8, 28),
            latitude=lat,
            longitude=lon,
            attributes={"location_name": name},
        )

    museums = [
        museum("m1", "Tokyo Metropolitan Art Museum", 35.7171959, 139.7727737),
        museum("m2", "Tokyo Metropolitan Teien Art Museum", 35.6368586, 139.7171918),
        museum("m3", "Museum of Contemporary Art Tokyo", 35.679714, 139.808002),
        museum("m4", "Tokyo Photographic Art Museum", 35.64159, 139.713278),
    ]
    mapping = assign_canonical_ids(museums)
    assert len({mapping[m.id] for m in museums}) == 4


def test_intra_source_multilocation_stays_separate():
    # Même URL de base, deux lieux distincts (multi-lieux) → deux clusters.
    base = "https://tokyocheapo.com/events/some-festival"
    a = mk(
        "tc",
        id="locA",
        title="Some Festival",
        url=f"{base}/",
        latitude=35.10,
        longitude=139.10,
        attributes={"location_name": "Place A"},
    )
    b = mk(
        "tc",
        id="locB",
        title="Some Festival",
        url=f"{base}/",
        latitude=36.90,
        longitude=140.90,
        attributes={"location_name": "Place B"},
    )
    mapping = assign_canonical_ids([a, b])
    assert mapping["locA"] != mapping["locB"]


def test_representative_prefers_event_with_coords():
    # Dans un cluster, on garde comme canonique celui qui a des coordonnées
    # (pour conserver un point sur la carte).
    with_coords = mk("hanabi", title="Sumida Fireworks", latitude=35.711, longitude=139.801)
    without_coords = mk(
        "tot",
        title="Sumida Fireworks",
        latitude=None,
        longitude=None,
        venue="Sumida",
        attributes={"venue_name": "Sumida"},
    )
    rep = canonical_representative([without_coords, with_coords])
    assert rep.id == with_coords.id


def test_representative_is_deterministic():
    a = mk("tc", title="X", latitude=35.1, longitude=139.1)
    b = mk("tc", title="X", latitude=35.1, longitude=139.1)
    assert canonical_representative([a, b]).id == canonical_representative([b, a]).id


def test_representative_single_member():
    a = mk("tc", title="Solo")
    assert canonical_representative([a]).id == a.id
