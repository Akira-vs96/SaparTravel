import pytest


@pytest.mark.parametrize("query", ["", "?lang=kk&page_size=1", "?sort=price_asc", "?category=Beach", "?min_price=300&max_price=10"])
def test_sli_catalog_endpoint_has_the_existing_catalog_contract(client, catalog, query):
    current = client.get("/api/v1/experiences" + query)
    measured = client.get("/api/v1/catalog" + query)
    assert measured.status_code == current.status_code
    assert measured.json() == current.json()
