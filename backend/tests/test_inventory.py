from tests.factories import make_member


async def _item(c, sku="GI-KID-120", name="Kids Gi", size="120", price="15.000", reorder=2):
    r = await c.post(
        "/api/inventory/items",
        json={
            "sku": sku,
            "name": name,
            "category": "uniform",
            "size": size,
            "unit_price": price,
            "reorder_level": reorder,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _stock(c, branch_id):
    rows = (await c.get("/api/inventory/stock", params={"branch_id": branch_id})).json()
    return {r["item"]["id"]: r["quantity"] for r in rows}


async def test_purchase_receive_transfer_flow(
    owner, manager, promenade_admin, bedaya_admin, branches
):
    prm, bdy = branches["promenade"], branches["bedaya"]
    gi = await _item(owner)
    belt = await _item(owner, sku="BELT-Y", name="Yellow belt", size=None, price="3.000")
    assert (await promenade_admin.post("/api/inventory/items", json={})).status_code == 403

    pr = (
        await promenade_admin.post(
            "/api/inventory/purchase-requests",
            json={
                "branch_id": prm,
                "vendor_name": "Intl Martial Supply",
                "vendor_type": "international",
                "lines": [
                    {"item_id": gi["id"], "quantity": 10},
                    {"item_id": belt["id"], "quantity": 20},
                ],
            },
        )
    ).json()
    assert pr["ref_no"] == f"PR-PRM-{pr['id']:05d}" and pr["status"] == "draft"
    base = f"/api/inventory/purchase-requests/{pr['id']}"
    # Cannot receive against an unapproved request.
    r = await promenade_admin.post(
        "/api/inventory/receipts",
        json={
            "branch_id": prm,
            "purchase_request_id": pr["id"],
            "lines": [{"item_id": gi["id"], "qty_received": 10}],
        },
    )
    assert r.status_code == 409
    await promenade_admin.post(f"{base}/submit")
    assert (
        await promenade_admin.post(f"{base}/decision", json={"approve": True})
    ).status_code == 403
    assert (await manager.post(f"{base}/decision", json={"approve": True})).json()[
        "status"
    ] == "approved"

    # 9 gis arrive (one short), belts missing entirely -> discrepancy recorded.
    r = await promenade_admin.post(
        "/api/inventory/receipts",
        json={
            "branch_id": prm,
            "purchase_request_id": pr["id"],
            "vendor_invoice_no": "INV-1",
            "lines": [{"item_id": gi["id"], "qty_received": 9}],
        },
    )
    assert r.status_code == 201, r.text
    grn = r.json()
    assert grn["has_discrepancy"] is True
    assert {(ln["item_id"], ln["qty_expected"], ln["qty_received"]) for ln in grn["lines"]} == {
        (gi["id"], 10, 9),
        (belt["id"], 20, 0),
    }
    assert (await _stock(owner, prm))[gi["id"]] == 9

    # Transfer 4 to Bedaya: leaves Promenade now, lands at Bedaya on receipt.
    r = await promenade_admin.post(
        "/api/inventory/transfers",
        json={
            "from_branch_id": prm,
            "to_branch_id": bdy,
            "lines": [{"item_id": gi["id"], "quantity": 4}],
        },
    )
    assert r.status_code == 201
    trf = r.json()
    assert (await _stock(owner, prm))[gi["id"]] == 5
    assert (await _stock(owner, bdy))[gi["id"]] == 0
    # Only the receiving branch can sign for it.
    assert (
        await promenade_admin.post(f"/api/inventory/transfers/{trf['id']}/receive")
    ).status_code == 403
    r = await bedaya_admin.post(f"/api/inventory/transfers/{trf['id']}/receive")
    assert r.json()["status"] == "received"
    assert (await _stock(owner, bdy))[gi["id"]] == 4
    assert (
        await bedaya_admin.post(f"/api/inventory/transfers/{trf['id']}/receive")
    ).status_code == 409

    # Cannot send more than is on hand.
    r = await promenade_admin.post(
        "/api/inventory/transfers",
        json={
            "from_branch_id": prm,
            "to_branch_id": bdy,
            "lines": [{"item_id": gi["id"], "quantity": 99}],
        },
    )
    assert r.status_code == 409
    assert (await _stock(owner, prm))[gi["id"]] == 5

    moves = (await owner.get("/api/inventory/movements", params={"branch_id": prm})).json()
    assert [m["reason"] for m in moves] == ["transfer_out", "receipt"]


async def test_local_vendor_once_per_month(owner, manager, promenade_admin, branches):
    prm = branches["promenade"]
    gi = await _item(owner)

    async def submitted_local():
        pr = (
            await promenade_admin.post(
                "/api/inventory/purchase-requests",
                json={
                    "branch_id": prm,
                    "vendor_name": "Local shop",
                    "vendor_type": "local",
                    "lines": [{"item_id": gi["id"], "quantity": 1}],
                },
            )
        ).json()
        await promenade_admin.post(f"/api/inventory/purchase-requests/{pr['id']}/submit")
        return f"/api/inventory/purchase-requests/{pr['id']}/decision"

    first, second = await submitted_local(), await submitted_local()
    assert (await manager.post(first, json={"approve": True})).status_code == 200
    assert (await manager.post(second, json={"approve": True})).status_code == 409
    assert (await manager.post(second, json={"approve": False})).status_code == 422
    r = await manager.post(second, json={"approve": False, "note": "Monthly local limit reached"})
    assert r.json()["status"] == "rejected"


async def test_sale_takes_stock_and_records_payment(owner, promenade_admin, branches):
    prm = branches["promenade"]
    gloves = await _item(owner, sku="GLV-12", name="Boxing gloves", size="12oz", price="12.500")
    await promenade_admin.post(
        "/api/inventory/receipts",
        json={
            "branch_id": prm,
            "lines": [{"item_id": gloves["id"], "qty_received": 3, "qty_expected": 3}],
        },
    )
    m = await make_member(promenade_admin, prm)
    r = await promenade_admin.post(
        "/api/inventory/sales",
        json={
            "branch_id": prm,
            "item_id": gloves["id"],
            "quantity": 2,
            "member_id": m["id"],
            "method": "knet",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json() == {
        "payment_id": r.json()["payment_id"],
        "amount": "25.000",
        "remaining_stock": 1,
    }
    pay = (await promenade_admin.get("/api/payments", params={"member_id": m["id"]})).json()[0]
    assert pay["category"] == "equipment" and pay["amount"] == "25.000"
    r = await promenade_admin.post(
        "/api/inventory/sales",
        json={"branch_id": prm, "item_id": gloves["id"], "quantity": 2, "method": "cash"},
    )
    assert r.status_code == 409
    # The failed sale left no payment behind.
    assert len((await promenade_admin.get("/api/payments")).json()) == 1
    low = (
        await owner.get("/api/inventory/stock", params={"branch_id": prm, "low_only": True})
    ).json()
    assert [x["item"]["sku"] for x in low] == ["GLV-12"]


async def test_monthly_count_adjusts_on_approval(owner, manager, promenade_admin, branches):
    prm = branches["promenade"]
    gi = await _item(owner)
    await promenade_admin.post(
        "/api/inventory/receipts",
        json={
            "branch_id": prm,
            "lines": [{"item_id": gi["id"], "qty_received": 10, "qty_expected": 10}],
        },
    )
    r = await promenade_admin.post(
        "/api/inventory/counts",
        json={
            "branch_id": prm,
            "period": "2026-09",
            "lines": [{"item_id": gi["id"], "counted_qty": 8}],
        },
    )
    count = r.json()
    assert count["lines"][0]["variance"] == -2
    url = f"/api/inventory/counts/{count['id']}/approve"
    assert (await promenade_admin.post(url)).status_code == 403
    assert (await manager.post(url)).status_code == 422  # variance without a reason
    dup = await promenade_admin.post(
        "/api/inventory/counts",
        json={
            "branch_id": prm,
            "period": "2026-09",
            "lines": [{"item_id": gi["id"], "counted_qty": 8}],
        },
    )
    assert dup.status_code == 409
    r = await promenade_admin.patch(
        f"/api/inventory/counts/{count['id']}",
        json={"lines": [{"item_id": gi["id"], "counted_qty": 8, "reason": "Damaged, written off"}]},
    )
    assert r.status_code == 200, r.text
    assert (await manager.post(url)).json()["status"] == "approved"
    assert (await _stock(owner, prm))[gi["id"]] == 8
