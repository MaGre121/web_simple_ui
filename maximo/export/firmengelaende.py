import json
from maximo.export.utils import slugify

def export_firmengelaende(tree, target_level, target_dir):
    def walk(nodes, level):
        for loc_id, node in nodes.items():
            if level == target_level:
                name = slugify(node.get("description", ""))
                location = node.get("location", loc_id)

                path = target_dir / f"{name}-({location}).json"
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(node, f, indent=2, ensure_ascii=False)
                continue

            walk(node.get("children", {}), level + 1)

    walk(tree, 0)
