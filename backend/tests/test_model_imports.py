def test_app_models_imports_cleanly():
    import app.models  # noqa: F401


def test_inventory_request_exports_request_status():
    from app.models.inventory_request import InventoryRequest, RequestStatus

    assert RequestStatus.PENDING.value == "PENDING"
    assert InventoryRequest.status.default.arg == "PENDING"
