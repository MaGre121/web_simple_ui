from maximo.export.utils import slugify
def index_assets_by_location(assets_raw: list[dict]) -> dict:
    assets_by_location: dict[str, dict] = {}

    for asset in assets_raw:
        location = asset.get("spi:location")
        assetnum = asset.get("spi:assetnum")

        if not location or not assetnum:
            continue  # kaputte Daten ignorieren

        assets_by_location.setdefault(location, {})[assetnum] = {
            "assetnum": assetnum,
            "description": slugify(asset.get("spi:description")),
            "itemnum": asset.get("spi:itemnum"),
            "serialnum": asset.get("spi:serialnum"),
        }

    return assets_by_location
