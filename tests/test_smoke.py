import akamai_techdocs_mcp


def test_version_defined() -> None:
    assert akamai_techdocs_mcp.__version__
    assert isinstance(akamai_techdocs_mcp.__version__, str)
