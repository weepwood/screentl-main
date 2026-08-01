from scripts.prepare_build_assets import version_tuple


def test_build_asset_version_is_four_part_integer_tuple():
    value = version_tuple()

    assert len(value) == 4
    assert all(isinstance(part, int) for part in value)
    assert value[:3] == (0, 2, 0)
