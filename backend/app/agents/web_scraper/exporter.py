import csv
import io
import json


def export(records: list[dict], format: str) -> str:
    if format == "json":
        return json.dumps(records, ensure_ascii=False, indent=2)
    keys = list(dict.fromkeys(k for row in records for k in row))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=keys)
    writer.writeheader()

    def safe(value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        if isinstance(value, str) and value.lstrip().startswith(
            ("=", "+", "-", "@", "\t", "\r")
        ):
            return "'" + value
        return value

    writer.writerows({k: safe(v) for k, v in row.items()} for row in records)
    return output.getvalue()
