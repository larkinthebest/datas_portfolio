from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import Settings


def test_health_and_authenticated_decimal_calculation(monkeypatch) -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        api_key="test-key",
        ai_external_processing_enabled=False,
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    with TestClient(main_module.create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        unauthorized = client.post(
            "/api/v1/calculations/depreciation",
            json={
                "acquisition_cost": "1200",
                "useful_life_months": 12,
                "start_date": "2025-01-01",
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
            },
        )
        assert unauthorized.status_code == 401
        response = client.post(
            "/api/v1/calculations/depreciation",
            headers={"X-API-Key": "test-key"},
            json={
                "acquisition_cost": "1200",
                "useful_life_months": 12,
                "start_date": "2025-01-01",
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
            },
        )
        assert response.status_code == 200
        assert response.json()["amount_for_period"] == "1200.00"
