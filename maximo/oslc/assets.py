from maximo.config.settings import OSLC_PARAMS_ASSETS, OSLC_ENDPOINT_ASSETS
from maximo.oslc.fetch import fetch_all_oslc
import logging
logger = logging.getLogger(__name__)

def _build_asset_params_for_location(location: str) -> dict:
    params = OSLC_PARAMS_ASSETS.copy()
    params["oslc.where"] = f'location="{location}"'
    return params

def add_asset(server, session, location, serialnumber, macaddress):
    ASSET = {
        "spi:itemnum": "CISCO.CATALYST.9200L.24P.4G", # masteritem (/maximo/oslc/os/mxitem)
        "spi:itemsetid": "ITARTIKL", # kann vom masteritem übernommen werden
        "spi:siteid": "BWS00001",
        "spi:orgid": "BTRBZ", # kann vom masteritem übernommen werden
        "spi:location": f"{location}",  # anpassen
        "spi:serialnum": f"{serialnumber}",
        "spi:assetspec": [ # werte werden vom masteritem vorgegeben (kann, nicht muss)
            {
                "spi:assetattrid": "BAM.MACADRESSE",
                "spi:alnvalue": f"{macaddress}",
                "spi:classstructureid": "2549"
            }
        ]
    }

    url = f"{server}{OSLC_ENDPOINT_ASSETS}"
    response = session.post(
        url,
        json=ASSET,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-public-uri": server  # manchmal nötig bei Maximo hinter Proxy
        },
        timeout=30
    )
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print(f"Body: {response.text[:1000]}")

    return 0

def fetch_assets_for_location(server, session, location: str) -> dict:
    assets = {}
    logger.debug("Fetching assets for location=%s", location)

    members = fetch_all_oslc(
        server=server,
        session=session,
        endpoint=OSLC_ENDPOINT_ASSETS,
        params=OSLC_PARAMS_ASSETS,
        max_pages=20
    )


    params = _build_asset_params_for_location(location)

    for asset in members:
        assetnum = asset.get("spi:assetnum")
        if not assetnum:
            continue  # kaputtes Asset → ignorieren

        assets[assetnum] = {
            "assetnum": assetnum,
            "description": asset.get("spi:description"),
            "itemnum": asset.get("spi:itemnum"),
            "serialnum": asset.get("spi:serialnum"),
        }

    logger.debug(
        "Fetched %d assets for location=%s",
        len(assets),
        location
    )

    return assets
