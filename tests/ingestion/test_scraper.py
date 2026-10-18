from unittest.mock import MagicMock, patch

import pytest
import requests

from optibot.ingestion import scraper


def _ok_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    return response


@patch("optibot.ingestion.scraper.time.sleep")
def test_get_page_retries_body_read_timeout(_sleep):
    session = MagicMock()
    session.get.side_effect = [requests.ConnectionError("Read timed out"), _ok_response({"articles": []})]

    assert scraper._get_page(session, "https://x") == {"articles": []}
    assert session.get.call_count == 2


@patch("optibot.ingestion.scraper.time.sleep")
def test_get_page_raises_after_last_attempt(_sleep):
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("Read timed out")

    with pytest.raises(requests.ConnectionError):
        scraper._get_page(session, "https://x")
    assert session.get.call_count == scraper.PAGE_ATTEMPTS
