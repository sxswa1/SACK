import pytest

from sack.knowledge.clients.tugraph_bolt import TuGraphBoltClient, TuGraphClientError


class FakeResult:
    def data(self):
        return [{"value": 1}]


class FakeSession:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def run(self, query, parameters):
        self.calls.append((query, parameters))
        return FakeResult()


class FakeDriver:
    def __init__(self):
        self.calls = []
        self.database = None
        self.closed = False

    def session(self, *, database):
        self.database = database
        return FakeSession(self.calls)

    def close(self):
        self.closed = True


def test_bolt_client_uses_database_and_parameters_without_interpolation():
    driver = FakeDriver()
    factory_calls = []

    def factory(uri, **kwargs):
        factory_calls.append((uri, kwargs))
        return driver

    client = TuGraphBoltClient(
        uri="bolt://server:7687",
        graph="sack_poc",
        user="reader",
        password="secret",
        driver_factory=factory,
    )
    rows = client.run("MATCH (n {uid: $uid}) RETURN n", {"uid": "abc"})

    assert rows == [{"value": 1}]
    assert driver.database == "sack_poc"
    assert driver.calls == [("MATCH (n {uid: $uid}) RETURN n", {"uid": "abc"})]
    assert factory_calls[0][1]["auth"] == ("reader", "secret")
    client.close()
    assert driver.closed


def test_bolt_client_rejects_non_bolt_uri():
    with pytest.raises(ValueError, match="Bolt URI"):
        TuGraphBoltClient(
            uri="http://server:7070",
            graph="sack",
            user="reader",
            password="secret",
            driver_factory=lambda *args, **kwargs: FakeDriver(),
        )


def test_bolt_client_maps_driver_errors():
    class BrokenDriver(FakeDriver):
        def session(self, *, database):
            raise RuntimeError("offline")

    client = TuGraphBoltClient(
        uri="bolt://server:7687",
        graph="sack",
        user="reader",
        password="secret",
        driver_factory=lambda *args, **kwargs: BrokenDriver(),
    )

    with pytest.raises(TuGraphClientError, match="query failed"):
        client.run("RETURN 1")
