import pytest
from pydantic import SecretStr

from app.core.config import Settings


@pytest.mark.parametrize("password", ["Chennai#44", "it's a #test", "p@ss:w/rd?+%&="])
def test_database_url_keeps_any_password(password):
    url = Settings(db_password=SecretStr(password), db_user="u@x").database_url("pymysql")
    assert url.password == password
    assert url.username == "u@x"
