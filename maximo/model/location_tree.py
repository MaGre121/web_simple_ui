def build_flat_structure(
    locations: list,
    assets: dict | None = None,
) -> dict:
    assets = assets or {}
    flat = {}

    for loc in locations:
        loc_id = loc.get("spi:location")
        if not loc_id:
            continue

        parent = None
        loch = loc.get("lochierarchy")
        if isinstance(loch, dict):
            parent = loch.get("parent")

        flat[loc_id] = {
            "location": loc_id,
            "description": loc.get("spi:description"),
            "siteid": loc.get("spi:siteid"),
            "parent": parent,
            "children": {},
            "assets": assets.get(loc_id, {}),
        }

    return flat


def build_tree(flat: dict) -> dict:
    tree = {}

    for loc_id, node in flat.items():
        parent = node["parent"]
        if parent and parent in flat:
            flat[parent]["children"][loc_id] = node
        else:
            tree[loc_id] = node

    return tree


def _prune_empty_locations(node: dict) -> bool:
    # Keep parents when they still contain child nodes with assets.
    children = node.get("children", {})
    to_delete = []

    for child_id, child in children.items():
        if not _prune_empty_locations(child):
            to_delete.append(child_id)

    for child_id in to_delete:
        del children[child_id]

    has_assets = bool(node.get("assets"))
    has_children = bool(children)

    return has_assets or has_children


def prune_tree(tree: dict) -> dict:
    pruned = {}

    for loc_id, node in tree.items():
        if _prune_empty_locations(node):
            pruned[loc_id] = node

    return pruned

