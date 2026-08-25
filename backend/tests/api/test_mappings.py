"""Tests for the source-mapping CRUD API (Task 6)."""


def _payload(source_name="Chase CSV export", target_kind="payment"):
    return {
        "source_name": source_name,
        "target_kind": target_kind,
        "column_map": {
            "date": "Post Date",
            "amount": "Trans Amt",
            "reference": "Memo",
            "counterparty": "Other Party",
        },
    }


def test_create_then_get_mapping_round_trips(client):
    create_response = client.post("/api/v1/mappings", json=_payload())
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["source_name"] == "Chase CSV export"
    assert created["target_kind"] == "payment"
    assert created["column_map"]["amount"] == "Trans Amt"
    assert "id" in created and "created_at" in created and "updated_at" in created

    get_response = client.get(f"/api/v1/mappings/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == created


def test_list_mappings_includes_created_mapping(client):
    created = client.post("/api/v1/mappings", json=_payload(source_name="Bank A")).json()

    list_response = client.get("/api/v1/mappings")
    assert list_response.status_code == 200
    ids = [row["id"] for row in list_response.json()]
    assert created["id"] in ids


def test_create_mapping_missing_required_column_map_field_is_rejected(client):
    payload = _payload()
    del payload["column_map"]["amount"]

    response = client.post("/api/v1/mappings", json=payload)
    assert response.status_code == 422


def test_create_mapping_duplicate_source_name_is_rejected(client):
    client.post("/api/v1/mappings", json=_payload(source_name="Dup Source"))

    response = client.post("/api/v1/mappings", json=_payload(source_name="Dup Source"))
    assert response.status_code == 409


def test_update_mapping_replaces_column_map(client):
    created = client.post("/api/v1/mappings", json=_payload(source_name="Wells Fargo")).json()

    updated_payload = _payload(source_name="Wells Fargo")
    updated_payload["column_map"]["reference"] = "Description"

    response = client.put(f"/api/v1/mappings/{created['id']}", json=updated_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["column_map"]["reference"] == "Description"
    assert body["id"] == created["id"]


def test_get_unknown_mapping_returns_404(client):
    response = client.get("/api/v1/mappings/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_update_unknown_mapping_returns_404(client):
    response = client.put(
        "/api/v1/mappings/00000000-0000-0000-0000-000000000000", json=_payload()
    )
    assert response.status_code == 404
