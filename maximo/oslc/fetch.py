def fetch_all_oslc(server, session, endpoint, params, max_pages):
    all_members = []
    url = f"{server}{endpoint}"
    page = 0

    while url and page < max_pages:
        response = session.get(
            url,
            headers={"Accept": "application/json"},
            params=params if page == 0 else None,
            timeout=30
        )

        print(f"➡️ Request Seite {page + 1}: {response.status_code}")
        if "application/json" not in response.headers.get("Content-Type", ""):
            raise RuntimeError("❌ Kein JSON – LTPA Token vermutlich abgelaufen")

        data = response.json()
        members = data.get("rdfs:member", [])
        if not members:
            break

        all_members.extend(members)

        url = (
            data.get("oslc:responseInfo", {})
                .get("oslc:nextPage", {})
                .get("rdf:resource")
        )
        page += 1

    return all_members

