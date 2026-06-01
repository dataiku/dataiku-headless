#!/usr/bin/env python3
"""Generate the shared benchmark fixture world."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml


SEED = 20260427
WORLD_DIR = Path(__file__).parent / "world"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _iso_day(start: date, offset: int) -> str:
    return (start + timedelta(days=offset)).isoformat()


def build_world() -> dict[str, object]:
    countries = [
        "United States",
        "France",
        "Germany",
        "Japan",
        "Brazil",
        "Canada",
        "Spain",
        "United Kingdom",
    ]
    plans = ["free", "pro", "team", "enterprise"]
    regions = ["East", "West", "North", "South"]
    tiers = ["VIP", "active", "new", "churned"]
    categories = ["Hardware", "Software", "Accessories", "Services"]
    event_types = ["view", "click", "search", "purchase", "support_ticket"]

    users = []
    signup_start = date(2023, 1, 1)
    for idx in range(1, 201):
        users.append(
            {
                "user_id": f"U{idx:04d}",
                "signup_date": _iso_day(signup_start, idx % 320),
                "plan": plans[idx % len(plans)],
                "country": countries[idx % len(countries)],
            }
        )

    customers = []
    for idx in range(1, 101):
        customer_id = "" if idx in {9, 27, 64, 88} else f"C{idx:03d}"
        customers.append(
            {
                "customer_id": customer_id,
                "name": f"Customer {idx:03d}",
                "tier": tiers[(idx - 1) % len(tiers)],
                "country": countries[(idx * 3) % len(countries)],
            }
        )

    products = []
    for idx in range(1, 51):
        unit_price = round(12 + idx * 1.85 + (idx % 5) * 0.4, 2)
        products.append(
            {
                "product_id": f"P{idx:03d}",
                "name": f"Product {idx:03d}",
                "category": categories[(idx - 1) % len(categories)],
                "unit_price": f"{unit_price:.2f}",
            }
        )

    product_lookup = {row["product_id"]: row for row in products}
    valid_customer_ids = [row["customer_id"] for row in customers if row["customer_id"]]

    orders = []
    order_start = date(2024, 1, 1)
    region_revenue: dict[str, float] = defaultdict(float)
    vip_revenue_by_country: dict[str, float] = defaultdict(float)
    monthly_category_revenue: dict[tuple[str, str], float] = defaultdict(float)

    for idx in range(1, 501):
        product_id = f"P{((idx - 1) % 50) + 1:03d}"
        customer_id = valid_customer_ids[(idx * 7) % len(valid_customer_ids)]
        region = regions[(idx - 1) % len(regions)]
        order_date = _iso_day(order_start, (idx * 3) % 365)

        base_price = float(product_lookup[product_id]["unit_price"])
        multiplier = 1 + ((idx % 9) * 0.13)
        amount_value = round(base_price * multiplier, 2)
        amount = f"{amount_value:.2f}"

        orders.append(
            {
                "order_id": f"O{idx:05d}",
                "customer_id": customer_id,
                "product_id": product_id,
                "region": region,
                "amount": amount,
                "date": order_date,
            }
        )

        region_revenue[region] += amount_value

        customer = customers[int(customer_id[1:]) - 1]
        if customer["tier"] == "VIP":
            vip_revenue_by_country[customer["country"]] += amount_value

        month = order_date[:7]
        category = product_lookup[product_id]["category"]
        monthly_category_revenue[(month, category)] += amount_value

    events = []
    event_start = datetime(2024, 2, 1, tzinfo=timezone.utc)
    for idx in range(1, 1001):
        timestamp = event_start + timedelta(minutes=idx * 17)
        user_id = users[(idx * 5) % len(users)]["user_id"]
        event_type = event_types[idx % len(event_types)]
        props = {
            "source": ["email", "ads", "organic", "partner"][idx % 4],
            "device": ["web", "ios", "android"][idx % 3],
            "value": idx % 11,
        }
        events.append(
            {
                "event_id": f"E{idx:05d}",
                "user_id": user_id,
                "event_type": event_type,
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "properties": json.dumps(props, sort_keys=True),
            }
        )

    ground_truth = {
        "seed": SEED,
        "row_counts": {
            "orders": len(orders),
            "customers": len(customers),
            "products": len(products),
            "events": len(events),
            "users": len(users),
        },
        "orders": {
            "sum_amount_by_region": {
                region: round(value, 2)
                for region, value in sorted(region_revenue.items())
            },
            "vip_revenue_by_country": {
                country: round(value, 2)
                for country, value in sorted(vip_revenue_by_country.items())
            },
            "monthly_category_revenue_sample": [
                {"month": month, "category": category, "revenue": round(value, 2)}
                for (month, category), value in sorted(
                    monthly_category_revenue.items()
                )[:12]
            ],
        },
    }

    return {
        "orders": orders,
        "customers": customers,
        "products": products,
        "events": events,
        "users": users,
        "ground_truth": ground_truth,
    }


def _generate_room_bookings() -> list[dict[str, str]]:
    """Room booking periods for interval_overlap scenario."""
    definitions = {
        "Alpha": [
            ("Occupied", date(2024, 1, 1), date(2024, 2, 15)),
            ("Maintenance", date(2024, 2, 16), date(2024, 3, 1)),
            ("Occupied", date(2024, 3, 2), date(2024, 5, 20)),
            ("Available", date(2024, 5, 21), date(2024, 6, 5)),
            ("Occupied", date(2024, 6, 6), date(2024, 6, 30)),
        ],
        "Beta": [
            ("Maintenance", date(2024, 1, 1), date(2024, 1, 31)),
            ("Occupied", date(2024, 2, 1), date(2024, 4, 10)),
            ("Available", date(2024, 4, 11), date(2024, 4, 20)),
            ("Occupied", date(2024, 4, 21), date(2024, 6, 15)),
            ("Maintenance", date(2024, 6, 16), date(2024, 6, 30)),
        ],
        "Gamma": [
            ("Occupied", date(2024, 1, 15), date(2024, 4, 5)),
            ("Available", date(2024, 4, 6), date(2024, 4, 30)),
            ("Occupied", date(2024, 5, 1), date(2024, 5, 30)),
            ("Available", date(2024, 6, 1), date(2024, 6, 30)),
        ],
        "Delta": [
            ("Available", date(2024, 1, 1), date(2024, 2, 29)),
            ("Occupied", date(2024, 3, 1), date(2024, 4, 30)),
            ("Maintenance", date(2024, 5, 1), date(2024, 5, 31)),
            ("Occupied", date(2024, 6, 1), date(2024, 6, 30)),
        ],
    }
    rows: list[dict[str, str]] = []
    for room_id, periods in definitions.items():
        for status, start, end in periods:
            rows.append(
                {
                    "room_id": room_id,
                    "status": status,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                }
            )
    return rows


def _compute_overlap_answer(
    bookings: list[dict[str, str]],
    entity_a: str = "Alpha",
    entity_b: str = "Beta",
    window_start: date = date(2024, 4, 1),
    window_end: date = date(2024, 6, 30),
    target_status: str = "Occupied",
) -> int:
    """Compute total overlap days between two entities within a window."""

    def _parse(d: str) -> date:
        return datetime.strptime(d, "%Y-%m-%d").date()

    a_periods: list[tuple[date, date]] = [
        (_parse(r["start_date"]), _parse(r["end_date"]))
        for r in bookings
        if r["room_id"] == entity_a and r["status"] == target_status
    ]
    b_periods: list[tuple[date, date]] = [
        (_parse(r["start_date"]), _parse(r["end_date"]))
        for r in bookings
        if r["room_id"] == entity_b and r["status"] == target_status
    ]

    total = 0
    for as_, ae in a_periods:
        for bs_, be in b_periods:
            overlap_start = max(as_, bs_, window_start)
            overlap_end = min(ae, be, window_end)
            if overlap_start < overlap_end:
                total += (overlap_end - overlap_start).days
    return total


def _generate_user_sessions() -> list[dict[str, str]]:
    """User login/logout sessions for session_gaps scenario.

    Users U1003 and U1007 have deliberate gaps > 48h between sessions.
    """

    def dt(d: int, h: int, m: int = 0) -> str:
        return datetime(2024, 3, d, h, m).isoformat()

    sessions: list[dict[str, str]] = []
    sid = 0

    def add(
        user: str, d: int, login_h: int, login_m: int, logout_h: int, logout_m: int
    ) -> None:
        nonlocal sid
        sid += 1
        sessions.append(
            {
                "session_id": f"S{sid:04d}",
                "user_id": user,
                "login_time": dt(d, login_h, login_m),
                "logout_time": dt(d, logout_h, logout_m),
            }
        )

    # U1001: 6 sessions, Mar 1-3, max gap ~15h
    for d, lh, lm, loh, lom in [
        (1, 8, 0, 10, 0),
        (1, 13, 0, 15, 30),
        (1, 18, 0, 20, 0),
        (2, 9, 0, 11, 0),
        (2, 15, 0, 17, 0),
        (3, 10, 0, 12, 0),
    ]:
        add("U1001", d, lh, lm, loh, lom)

    # U1002: 7 sessions, Mar 1-3, max gap ~12.5h
    for d, lh, lm, loh, lom in [
        (1, 9, 0, 11, 0),
        (1, 14, 0, 16, 0),
        (1, 19, 0, 21, 0),
        (2, 8, 0, 10, 30),
        (2, 13, 0, 15, 0),
        (2, 18, 0, 20, 30),
        (3, 9, 0, 11, 0),
    ]:
        add("U1002", d, lh, lm, loh, lom)

    # U1003: 6 sessions, 62h gap between session 3 and 4
    for d, lh, lm, loh, lom in [
        (1, 8, 0, 10, 0),
        (1, 12, 0, 14, 30),
        (1, 17, 0, 19, 0),
        (4, 9, 0, 11, 30),
        (4, 15, 0, 17, 0),
        (4, 20, 0, 22, 0),
    ]:
        add("U1003", d, lh, lm, loh, lom)

    # U1004: 5 sessions, Mar 2-4, max gap ~15h
    for d, lh, lm, loh, lom in [
        (2, 10, 0, 12, 0),
        (2, 16, 0, 18, 0),
        (3, 9, 0, 11, 0),
        (3, 15, 0, 17, 0),
        (4, 8, 0, 10, 0),
    ]:
        add("U1004", d, lh, lm, loh, lom)

    # U1005: 8 sessions, Mar 1-4, max gap ~10h
    for d, lh, lm, loh, lom in [
        (1, 8, 0, 10, 0),
        (1, 12, 0, 14, 0),
        (1, 17, 0, 19, 0),
        (2, 9, 0, 11, 0),
        (2, 14, 0, 16, 0),
        (3, 10, 0, 12, 0),
        (3, 17, 0, 19, 0),
        (4, 8, 0, 10, 0),
    ]:
        add("U1005", d, lh, lm, loh, lom)

    # U1006: 6 sessions, Mar 2-4, max gap ~13h
    for d, lh, lm, loh, lom in [
        (2, 9, 0, 11, 0),
        (2, 14, 0, 16, 0),
        (2, 19, 0, 21, 0),
        (3, 10, 0, 12, 0),
        (3, 16, 0, 18, 0),
        (4, 9, 0, 11, 0),
    ]:
        add("U1006", d, lh, lm, loh, lom)

    # U1007: 5 sessions, 72h gap between session 2 and 3
    for d, lh, lm, loh, lom in [
        (1, 8, 0, 10, 0),
        (1, 13, 0, 15, 0),
        (4, 15, 0, 17, 0),
        (4, 21, 0, 23, 0),
        (5, 8, 0, 10, 0),
    ]:
        add("U1007", d, lh, lm, loh, lom)

    # U1008: 7 sessions, Mar 2-5, max gap ~10h
    for d, lh, lm, loh, lom in [
        (2, 10, 0, 12, 0),
        (2, 15, 0, 17, 0),
        (2, 20, 0, 22, 0),
        (3, 9, 0, 11, 0),
        (3, 14, 0, 16, 0),
        (4, 10, 0, 12, 0),
        (5, 8, 0, 10, 0),
    ]:
        add("U1008", d, lh, lm, loh, lom)

    # U1009: 6 sessions, Mar 2-4, max gap ~12h
    for d, lh, lm, loh, lom in [
        (2, 8, 0, 10, 0),
        (2, 13, 0, 15, 0),
        (3, 9, 0, 11, 0),
        (3, 14, 0, 16, 0),
        (3, 19, 0, 21, 0),
        (4, 8, 0, 10, 0),
    ]:
        add("U1009", d, lh, lm, loh, lom)

    # U1010: 5 sessions, Mar 1-2, max gap ~8h
    for d, lh, lm, loh, lom in [
        (1, 9, 0, 11, 0),
        (1, 14, 0, 16, 0),
        (1, 19, 0, 21, 0),
        (2, 9, 0, 11, 0),
        (2, 14, 0, 16, 0),
    ]:
        add("U1010", d, lh, lm, loh, lom)

    return sessions


def _compute_gaps_answer(
    sessions: list[dict[str, str]], threshold_hours: float = 48.0
) -> list[dict]:
    """Find users with max gap (next login - prev logout) > threshold_hours."""
    by_user: dict[str, list[tuple[datetime, datetime]]] = {}
    for s in sessions:
        by_user.setdefault(s["user_id"], []).append(
            (
                datetime.fromisoformat(s["login_time"]),
                datetime.fromisoformat(s["logout_time"]),
            )
        )

    result: list[dict] = []
    for uid in sorted(by_user):
        times = sorted(by_user[uid], key=lambda x: x[0])
        max_gap = 0.0
        for i in range(1, len(times)):
            gap = (times[i][0] - times[i - 1][1]).total_seconds() / 3600
            if gap > max_gap:
                max_gap = gap
        if max_gap > threshold_hours:
            result.append({"user_id": uid, "max_gap_hours": round(max_gap, 1)})

    result.sort(key=lambda r: -r["max_gap_hours"])
    return result


def _generate_stores() -> list[dict[str, str]]:
    return [
        {
            "store_id": "S001",
            "name": "Paris Boutique",
            "geom": "POINT (2.3522 48.8566)",
            "city": "Paris",
        },
        {
            "store_id": "S002",
            "name": "Tokyo Hub",
            "geom": "POINT (139.6917 35.6895)",
            "city": "Tokyo",
        },
        {
            "store_id": "S003",
            "name": "New York Flagship",
            "geom": "POINT (-74.006 40.7128)",
            "city": "New York",
        },
        {
            "store_id": "S004",
            "name": "London Store",
            "geom": "POINT (-0.1276 51.5074)",
            "city": "London",
        },
        {
            "store_id": "S005",
            "name": "Berlin Outlet",
            "geom": "POINT (13.405 52.52)",
            "city": "Berlin",
        },
        {
            "store_id": "S006",
            "name": "Sydney Branch",
            "geom": "POINT (151.2093 -33.8688)",
            "city": "Sydney",
        },
        {
            "store_id": "S007",
            "name": "Sao Paulo Shop",
            "geom": "POINT (-46.6333 -23.5505)",
            "city": "Sao Paulo",
        },
        {
            "store_id": "S008",
            "name": "Mumbai Store",
            "geom": "POINT (72.8777 19.076)",
            "city": "Mumbai",
        },
        {
            "store_id": "S009",
            "name": "Cairo Location",
            "geom": "POINT (31.2357 30.0444)",
            "city": "Cairo",
        },
        {
            "store_id": "S010",
            "name": "Toronto Branch",
            "geom": "POINT (-79.3832 43.6532)",
            "city": "Toronto",
        },
    ]


def _generate_warehouses() -> list[dict[str, str]]:
    return [
        {
            "warehouse_id": "W001",
            "name": "Europe Hub",
            "geom": "POINT (2.3488 48.8534)",
            "region": "Europe",
        },
        {
            "warehouse_id": "W002",
            "name": "Asia Pacific Hub",
            "geom": "POINT (139.7104 35.6762)",
            "region": "APAC",
        },
        {
            "warehouse_id": "W003",
            "name": "Americas Hub",
            "geom": "POINT (-74.006 40.7128)",
            "region": "Americas",
        },
    ]


def _generate_vendors() -> list[dict[str, str]]:
    return [
        {
            "vendor_id": "V001",
            "vendor_name": "Best Hardware Supply",
            "product_category": "Harware",
        },
        {
            "vendor_id": "V002",
            "vendor_name": "Soft Solutions",
            "product_category": "Softwaare",
        },
        {
            "vendor_id": "V003",
            "vendor_name": "Accessory World",
            "product_category": "Accesories",
        },
        {
            "vendor_id": "V004",
            "vendor_name": "Service Pro",
            "product_category": "Servises",
        },
        {
            "vendor_id": "V005",
            "vendor_name": "Hardware Plus",
            "product_category": "Hardware",
        },
        {
            "vendor_id": "V006",
            "vendor_name": "SoftSource",
            "product_category": "Sofware",
        },
        {
            "vendor_id": "V007",
            "vendor_name": "Accessories R Us",
            "product_category": "Accessorie",
        },
        {
            "vendor_id": "V008",
            "vendor_name": "Enterprise Services",
            "product_category": "Servces",
        },
        {
            "vendor_id": "V009",
            "vendor_name": "Hardware Direct",
            "product_category": "Hardware",
        },
        {"vendor_id": "V010", "vendor_name": "SoftCo", "product_category": "Software"},
        {
            "vendor_id": "V011",
            "vendor_name": "Accessory Mart",
            "product_category": "Accessories",
        },
        {
            "vendor_id": "V012",
            "vendor_name": "Service Central",
            "product_category": "Service",
        },
    ]


def main() -> None:
    world = build_world()

    _write_csv(
        WORLD_DIR / "orders.csv",
        ["order_id", "customer_id", "product_id", "region", "amount", "date"],
        world["orders"],
    )
    _write_csv(
        WORLD_DIR / "customers.csv",
        ["customer_id", "name", "tier", "country"],
        world["customers"],
    )
    _write_csv(
        WORLD_DIR / "products.csv",
        ["product_id", "name", "category", "unit_price"],
        world["products"],
    )
    _write_csv(
        WORLD_DIR / "events.csv",
        ["event_id", "user_id", "event_type", "timestamp", "properties"],
        world["events"],
    )
    _write_csv(
        WORLD_DIR / "users.csv",
        ["user_id", "signup_date", "plan", "country"],
        world["users"],
    )

    stores = _generate_stores()
    _write_csv(
        WORLD_DIR / "stores.csv",
        ["store_id", "name", "geom", "city"],
        stores,
    )
    warehouses = _generate_warehouses()
    _write_csv(
        WORLD_DIR / "warehouses.csv",
        ["warehouse_id", "name", "geom", "region"],
        warehouses,
    )

    vendors = _generate_vendors()
    _write_csv(
        WORLD_DIR / "vendors.csv",
        ["vendor_id", "vendor_name", "product_category"],
        vendors,
    )

    room_bookings = _generate_room_bookings()
    _write_csv(
        WORLD_DIR / "room_bookings.csv",
        ["room_id", "status", "start_date", "end_date"],
        room_bookings,
    )

    user_sessions = _generate_user_sessions()
    _write_csv(
        WORLD_DIR / "user_sessions.csv",
        ["session_id", "user_id", "login_time", "logout_time"],
        user_sessions,
    )

    overlap_answer = _compute_overlap_answer(room_bookings)
    gaps_answer = _compute_gaps_answer(user_sessions)

    ground_truth = world["ground_truth"]
    ground_truth["row_counts"]["stores"] = len(stores)
    ground_truth["row_counts"]["warehouses"] = len(warehouses)
    ground_truth["row_counts"]["vendors"] = len(vendors)
    ground_truth["row_counts"]["room_bookings"] = len(room_bookings)
    ground_truth["row_counts"]["user_sessions"] = len(user_sessions)
    ground_truth["room_bookings"] = {"alpha_beta_overlap_q2_2024": overlap_answer}
    ground_truth["user_sessions"] = {
        "long_gap_users": gaps_answer,
    }

    with open(WORLD_DIR / "ground_truth.yaml", "w") as f:
        yaml.safe_dump(ground_truth, f, sort_keys=False)


if __name__ == "__main__":
    main()
