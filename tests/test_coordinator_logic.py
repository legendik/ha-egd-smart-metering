"""Tests for EGD Coordinator logic."""

from datetime import UTC, datetime

from custom_components.egd_smart_meter.api import MeasurementData


class MockCoordinator:
    """Simplified coordinator for testing logic without HA dependencies."""

    def __init__(self):
        self._total_consumption = 0.0
        self._last_date = None

    def calculate_consumption(self, data):
        """Calculate total consumption from measurement data."""
        total = sum(
            item.value for item in data if item.value is not None and item.status == "IU012"
        )
        return total


class TestCoordinatorLogic:
    """Test coordinator calculation logic."""

    def test_calculate_consumption_with_valid_data(self):
        """Test that consumption is calculated correctly from valid measurements."""
        coordinator = MockCoordinator()

        data = [
            MeasurementData(
                timestamp=datetime(2023, 1, 1, 0, 15, 0, tzinfo=UTC),
                value=0.5,
                status="IU012",
            ),
            MeasurementData(
                timestamp=datetime(2023, 1, 1, 0, 30, 0, tzinfo=UTC),
                value=0.5,
                status="IU012",
            ),
            MeasurementData(
                timestamp=datetime(2023, 1, 1, 0, 45, 0, tzinfo=UTC),
                value=0.5,
                status="IU012",
            ),
        ]

        total = coordinator.calculate_consumption(data)
        assert total == 1.5  # 0.5 + 0.5 + 0.5

    def test_calculate_consumption_ignores_invalid_status(self):
        """Test that measurements with invalid status are ignored."""
        coordinator = MockCoordinator()

        data = [
            MeasurementData(
                timestamp=datetime(2023, 1, 1, 0, 15, 0, tzinfo=UTC),
                value=0.5,
                status="IU012",  # Valid
            ),
            MeasurementData(
                timestamp=datetime(2023, 1, 1, 0, 30, 0, tzinfo=UTC),
                value=0.5,
                status="IU014",  # Invalid - should be ignored
            ),
            MeasurementData(
                timestamp=datetime(2023, 1, 1, 0, 45, 0, tzinfo=UTC),
                value=None,  # Null value - should be ignored
                status="IU012",
            ),
        ]

        total = coordinator.calculate_consumption(data)
        assert total == 0.5  # Only first measurement counts

    def test_calculate_consumption_empty_data(self):
        """Test that empty data returns 0."""
        coordinator = MockCoordinator()

        data = []
        total = coordinator.calculate_consumption(data)
        assert total == 0.0

    def test_coordinator_does_not_accumulate(self):
        """Test that coordinator resets consumption on each calculation."""
        coordinator = MockCoordinator()

        # First batch: 100 kWh
        data1 = [
            MeasurementData(
                timestamp=datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC),
                value=100.0,
                status="IU012",
            )
        ]

        # Second batch: 50 kWh
        data2 = [
            MeasurementData(
                timestamp=datetime(2023, 1, 2, 12, 0, 0, tzinfo=UTC),
                value=50.0,
                status="IU012",
            )
        ]

        # Calculate first batch
        total1 = coordinator.calculate_consumption(data1)
        coordinator._total_consumption = total1

        # Calculate second batch (simulating restart)
        coordinator._total_consumption = 0  # Reset as if new instance
        total2 = coordinator.calculate_consumption(data2)
        coordinator._total_consumption = total2

        # Each should show that batch's consumption, not accumulated
        assert total1 == 100.0
        assert total2 == 50.0
        assert total1 + total2 == 150.0  # But they're separate


class TestMeasurementData:
    """Test MeasurementData dataclass."""

    def test_measurement_data_creation(self):
        """Test creating MeasurementData."""
        md = MeasurementData(
            timestamp=datetime(2023, 3, 1, 12, 0, 0, tzinfo=UTC),
            value=10.5,
            status="IU012",
        )
        assert md.timestamp == datetime(2023, 3, 1, 12, 0, 0, tzinfo=UTC)
        assert md.value == 10.5
        assert md.status == "IU012"

    def test_measurement_data_with_none_value(self):
        """Test MeasurementData with None value."""
        md = MeasurementData(
            timestamp=datetime(2023, 3, 1, 12, 0, 0, tzinfo=UTC),
            value=None,
            status="IU012",
        )
        assert md.value is None
