from uuid import uuid4

import httpx


async def create_tag(client: httpx.AsyncClient, name: str, color_key: str = "cyan") -> dict:
    response = await client.post("/tags", json={"name": name, "color_key": color_key})
    assert response.status_code == 201
    return response.json()


async def create_target(client: httpx.AsyncClient, name: str, tag_ids: list[str]) -> dict:
    response = await client.post(
        "/targets", json={"name": name, "url": "https://93.184.216.34", "tag_ids": tag_ids}
    )
    assert response.status_code == 201
    return response.json()


async def test_tags_crud_and_case_insensitive_unique_name(client: httpx.AsyncClient):
    production = await create_tag(client, "Production", "emerald")
    assert production["name"] == "Production"
    assert production["target_count"] == 0

    duplicate = await client.post("/tags", json={"name": " production ", "color_key": "cyan"})
    assert duplicate.status_code == 409

    updated = await client.patch(
        f"/tags/{production['id']}", json={"name": "Live", "color_key": "rose"}
    )
    assert updated.status_code == 200
    assert updated.json()["color_key"] == "rose"

    deleted = await client.delete(f"/tags/{production['id']}")
    assert deleted.status_code == 204
    assert (await client.get("/tags")).json()["items"] == []


async def test_target_tags_filter_and_deleting_tag_preserves_target(client: httpx.AsyncClient):
    production = await create_tag(client, "Production")
    hospital = await create_tag(client, "Hospital", "blue")
    first = await create_target(client, "first", [production["id"], hospital["id"]])
    second = await create_target(client, "second", [hospital["id"]])

    assert [tag["name"] for tag in first["tags"]] == ["Hospital", "Production"]
    any_response = await client.get(
        f"/targets/page?tag_ids={production['id']}&tag_ids={hospital['id']}"
    )
    assert any_response.status_code == 200
    assert {item["id"] for item in any_response.json()["items"]} == {first["id"], second["id"]}

    all_response = await client.get(
        f"/targets/page?tag_ids={production['id']}&tag_ids={hospital['id']}&tag_match=all"
    )
    assert [item["id"] for item in all_response.json()["items"]] == [first["id"]]

    cleared = await client.patch(f"/targets/{first['id']}", json={"tag_ids": []})
    assert cleared.status_code == 200
    assert cleared.json()["tags"] == []

    removed = await client.delete(f"/tags/{hospital['id']}")
    assert removed.status_code == 204
    target_response = await client.get(f"/targets/{second['id']}")
    assert target_response.status_code == 200
    assert target_response.json()["tags"] == []


async def test_target_tag_ids_are_validated_atomically(client: httpx.AsyncClient):
    target = await create_target(client, "third", [])
    response = await client.patch(f"/targets/{target['id']}", json={"tag_ids": [str(uuid4())]})
    assert response.status_code == 400
    assert (await client.get(f"/targets/{target['id']}")).json()["tags"] == []
