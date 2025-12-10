import sys
import types


def _inject_fakes():
    """Inject minimal fake modules for pyodbc, sqlalchemy and azure.identity
    so tests can import `azure_db` without installing heavy native deps.
    """
    # Fake pyodbc
    fake_pyodbc = types.ModuleType("pyodbc")
    fake_pyodbc._drivers = ["ODBC Driver 18 for SQL Server"]

    def drivers():
        return list(fake_pyodbc._drivers)

    fake_pyodbc.drivers = drivers

    # Fake sqlalchemy and submodules
    fake_sqlalchemy = types.ModuleType("sqlalchemy")

    class FakeEngine:
        def connect(self):
            class ConnCtx:
                def __enter__(self_inner):
                    class Conn:
                        def exec_driver_sql(self, sql):
                            return None

                    return Conn()

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return ConnCtx()


    def create_engine(url, connect_args=None):
        return FakeEngine()


    fake_sqlalchemy.create_engine = create_engine

    fake_sqla_engine = types.ModuleType("sqlalchemy.engine")

    class URL:
        @staticmethod
        def create(*args, **kwargs):
            # return a simple placeholder
            return (args, kwargs)


    fake_sqla_engine.URL = URL

    fake_sqla_exc = types.ModuleType("sqlalchemy.exc")

    class OperationalError(Exception):
        pass


    fake_sqla_exc.OperationalError = OperationalError

    # Fake azure.identity
    fake_azure = types.ModuleType("azure")
    fake_azure_identity = types.ModuleType("azure.identity")

    class FakeCred:
        def get_token(self, scope):
            class T:
                token = "fake-token"


            return T()


    fake_azure_identity.DefaultAzureCredential = FakeCred

    # Insert into sys.modules before importing azure_db
    sys.modules["pyodbc"] = fake_pyodbc
    sys.modules["sqlalchemy"] = fake_sqlalchemy
    sys.modules["sqlalchemy.engine"] = fake_sqla_engine
    sys.modules["sqlalchemy.exc"] = fake_sqla_exc
    sys.modules["azure"] = fake_azure
    sys.modules["azure.identity"] = fake_azure_identity


# Prepare fakes and then import the module under test
_inject_fakes()

import azure_db


def test_list_odbc_drivers():
    drivers = azure_db.list_odbc_drivers()
    assert isinstance(drivers, list)
    assert "ODBC Driver 18 for SQL Server" in drivers


def test_get_access_token():
    token = azure_db.get_access_token()
    # our fake returns 'fake-token'
    assert token == "fake-token"


def test_get_engine_prefers_token():
    eng = azure_db.get_engine(prefer_token=True)
    # Engine should expose a 'connect' method (FakeEngine)
    assert hasattr(eng, "connect")
