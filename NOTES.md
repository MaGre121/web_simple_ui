## Maximo Update assetspec
example function for update (working)
import base64
from maximo.config.settings import OSLC_ENDPOINT_ASSETS

### build URL from assetnum & siteid
```
def _asset_href(server: str, assetnum: str, siteid: str) -> str:
    raw = f"{assetnum}/{siteid}"
    b64 = base64.b64encode(raw.encode()).decode().rstrip("=")
    b64 = b64.replace("+", "-").replace("/", "_")
    return f"{server}{OSLC_ENDPOINT_ASSETS}/_{b64}-"
```

### update function with merge (important! without merge existing values will be deleted)
```
def update_asset_specs(server, session, assetnum, siteid, specs: list[dict]):
    """
    specs = [
        {"assetattrid": "BAM.MACADRESSE", "alnvalue": "AA:BB:CC:DD:EE:FF"},
        {"assetattrid": "BAM.HWREVISION", "alnvalue": "rev 3"},
    ]
    """
    payload = {
        "spi:assetspec": [
            {
                "spi:assetattrid": s["assetattrid"],
                "spi:linearassetspecid": 0,
                "spi:alnvalue": s["alnvalue"],
            }
            for s in specs
        ]
    }

    url = _asset_href(server, assetnum, siteid)
    resp = session.post(
        url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-method-override": "PATCH",
            "PATCHTYPE": "MERGE",
            "properties": "assetspec",
            "x-public-uri": server,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Update failed {resp.status_code}: {resp.text[:500]}")

    return resp.json()
```