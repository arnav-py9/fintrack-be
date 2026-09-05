import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.endpoints import client_revenue_endpoint as endpoint


def run(coro):
    return asyncio.run(coro)


def matches(doc, query):
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict) and "$ne" in expected:
            if actual == expected["$ne"]:
                return False
        elif actual != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self.docs = [deepcopy(doc) for doc in docs]

    def sort(self, key, direction):
        self.docs.sort(key=lambda doc: doc.get(key, ""), reverse=direction < 0)
        return self

    async def to_list(self, length=None):
        return self.docs


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]

    def find(self, query):
        return FakeCursor([doc for doc in self.docs if matches(doc, query)])

    async def find_one(self, query):
        return next((deepcopy(doc) for doc in self.docs if matches(doc, query)), None)

    async def insert_one(self, doc):
        stored = deepcopy(doc)
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    async def update_one(self, query, operation):
        for doc in self.docs:
            if matches(doc, query):
                doc.update(deepcopy(operation.get("$set", {})))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


@pytest.fixture
def database(monkeypatch):
    client_id = ObjectId()
    inactive_client_id = ObjectId()
    other_client_id = ObjectId()
    batch_id = ObjectId()
    other_batch_id = ObjectId()
    collections = {
        "client_revenue_clients": FakeCollection([
            {"_id": client_id, "user_id": "user-1", "name": "Client", "status": "active"},
            {"_id": inactive_client_id, "user_id": "user-1", "name": "Inactive", "status": "inactive"},
            {"_id": other_client_id, "user_id": "user-2", "name": "Other", "status": "active"},
        ]),
        "client_revenue_batches": FakeCollection([
            {
                "_id": batch_id,
                "user_id": "user-1",
                "clientId": str(client_id),
                "batchName": "Batch 1",
                "committedVideos": 3,
                "committedValue": 300,
                "status": "active",
            },
            {
                "_id": other_batch_id,
                "user_id": "user-2",
                "clientId": str(other_client_id),
                "batchName": "Other batch",
                "committedVideos": 3,
                "committedValue": 300,
                "status": "active",
            },
        ]),
        "client_revenue_payments": FakeCollection(),
        "client_revenue_deliveries": FakeCollection(),
        "client_revenue_settlements": FakeCollection(),
    }
    monkeypatch.setattr(endpoint, "get_collection", lambda name: collections[name])
    return SimpleNamespace(
        collections=collections,
        client_id=str(client_id),
        inactive_client_id=str(inactive_client_id),
        other_client_id=str(other_client_id),
        batch_id=str(batch_id),
        other_batch_id=str(other_batch_id),
    )


def assert_http_error(call, status_code):
    with pytest.raises(HTTPException) as error:
        run(call)
    assert error.value.status_code == status_code


def test_batch_creation_enforces_client_ownership_and_active_batch_rule(database):
    payload = dict(
        batchName="New batch",
        committedVideos=2,
        committedValue=200,
        startDate="2026-09-05",
    )
    assert_http_error(
        endpoint.add_batch(endpoint.BatchCreate(clientId=database.other_client_id, **payload), "user-1"),
        404,
    )
    assert_http_error(
        endpoint.add_batch(endpoint.BatchCreate(clientId=database.inactive_client_id, **payload), "user-1"),
        409,
    )
    assert_http_error(
        endpoint.add_batch(endpoint.BatchCreate(clientId=database.client_id, **payload), "user-1"),
        409,
    )


def test_payment_rejects_invalid_or_unowned_batch(database):
    assert_http_error(
        endpoint.add_payment(
            endpoint.PaymentCreate(batchId="not-an-object-id", amount=10, date="2026-09-05"),
            "user-1",
        ),
        400,
    )
    assert_http_error(
        endpoint.add_payment(
            endpoint.PaymentCreate(batchId=database.other_batch_id, amount=10, date="2026-09-05"),
            "user-1",
        ),
        404,
    )


def test_delivery_caps_progress_and_automatically_completes_batch(database):
    deliveries = database.collections["client_revenue_deliveries"]
    deliveries.docs.append({
        "_id": ObjectId(),
        "user_id": "user-1",
        "batchId": database.batch_id,
        "videosCompleted": 1,
    })
    result = run(endpoint.add_delivery(
        endpoint.DeliveryCreate(
            batchId=database.batch_id,
            videosCompleted=2,
            date="2026-09-05",
        ),
        "user-1",
    ))
    assert result["videosCompleted"] == 2
    batch = run(database.collections["client_revenue_batches"].find_one(
        {"_id": ObjectId(database.batch_id)}
    ))
    assert batch["status"] == "completed"
    assert_http_error(
        endpoint.add_delivery(
            endpoint.DeliveryCreate(
                batchId=database.batch_id,
                videosCompleted=1,
                date="2026-09-05",
            ),
            "user-1",
        ),
        409,
    )


def test_settlement_cannot_exceed_earned_revenue(database):
    database.collections["client_revenue_deliveries"].docs.append({
        "_id": ObjectId(),
        "user_id": "user-1",
        "batchId": database.batch_id,
        "videosCompleted": 2,
    })
    database.collections["client_revenue_settlements"].docs.append({
        "_id": ObjectId(),
        "user_id": "user-1",
        "batchId": database.batch_id,
        "amount": 50,
    })
    assert_http_error(
        endpoint.add_settlement(
            endpoint.SettlementCreate(
                batchId=database.batch_id,
                amount=151,
                date="2026-09-05",
                fromAccount="Personal",
                toAccount="Business",
            ),
            "user-1",
        ),
        409,
    )
    result = run(endpoint.add_settlement(
        endpoint.SettlementCreate(
            batchId=database.batch_id,
            amount=150,
            date="2026-09-05",
            fromAccount="Personal",
            toAccount="Business",
        ),
        "user-1",
    ))
    assert result["amount"] == 150


def test_update_and_archive_guards(database):
    database.collections["client_revenue_deliveries"].docs.append({
        "_id": ObjectId(),
        "user_id": "user-1",
        "batchId": database.batch_id,
        "videosCompleted": 2,
    })
    assert_http_error(
        endpoint.update_batch(
            database.batch_id,
            endpoint.BatchUpdate(committedVideos=1),
            "user-1",
        ),
        409,
    )
    assert_http_error(endpoint.archive_client(database.client_id, "user-1"), 409)
    assert_http_error(endpoint.cancel_batch(database.batch_id, "user-1"), 409)


def test_client_update_and_archive_succeed(database):
    updated = run(endpoint.update_client(
        database.inactive_client_id,
        endpoint.ClientUpdate(name="Renamed client", status="active"),
        "user-1",
    ))
    assert updated["name"] == "Renamed client"
    assert updated["status"] == "active"

    result = run(endpoint.archive_client(database.inactive_client_id, "user-1"))
    assert result == {"message": "Client archived"}
    stored = run(database.collections["client_revenue_clients"].find_one(
        {"_id": ObjectId(database.inactive_client_id)}
    ))
    assert stored["status"] == "inactive"


def test_empty_batch_can_be_cancelled(database):
    result = run(endpoint.cancel_batch(database.batch_id, "user-1"))
    assert result == {"message": "Batch cancelled"}
    stored = run(database.collections["client_revenue_batches"].find_one(
        {"_id": ObjectId(database.batch_id)}
    ))
    assert stored["status"] == "cancelled"


def test_manual_completion_requires_all_deliveries(database):
    assert_http_error(endpoint.complete_batch(database.batch_id, "user-1"), 409)
    database.collections["client_revenue_deliveries"].docs.append({
        "_id": ObjectId(),
        "user_id": "user-1",
        "batchId": database.batch_id,
        "videosCompleted": 3,
    })
    completed = run(endpoint.complete_batch(database.batch_id, "user-1"))
    assert completed["status"] == "completed"


def test_router_exposes_crud_and_lifecycle_routes():
    routes = {
        (route.path, method)
        for route in endpoint.router.routes
        for method in getattr(route, "methods", set())
    }
    expected = {
        ("/", "GET"),
        ("/clients", "POST"),
        ("/clients/{client_id}", "PUT"),
        ("/clients/{client_id}", "DELETE"),
        ("/batches", "POST"),
        ("/batches/{batch_id}", "PUT"),
        ("/batches/{batch_id}", "DELETE"),
        ("/payments", "POST"),
        ("/deliveries", "POST"),
        ("/settlements", "POST"),
        ("/batches/{batch_id}/complete", "PATCH"),
        ("/batches/{batch_id}/end", "PATCH"),
    }
    assert expected <= routes
