#!/usr/bin/env python3
"""Build a DynamoDB UpdateItem request from a plain-JSON item.

Writes two files:
  argv[1]  the request body, for `aws dynamodb update-item --cli-input-json file://...`
  argv[2]  a short markdown fragment naming the key, appended to the step summary by the
           caller *after* the write succeeds, so the summary never reports a failed write

Sending is left to the AWS CLI, which handles credentials and retries.

This produces a MERGE, not a replace: the generated UpdateItem SETs only the attributes present in
the payload, so attributes written by other jobs survive. Do not change it to PutItem, which
deletes every attribute absent from the payload.

Granularity is top-level: a map-valued attribute is replaced wholesale rather than merged
key-by-key, so stale sub-keys cannot linger. Supply the complete map for any attribute you write.
"""

from __future__ import annotations

import json
import os
import sys


def to_ddb(value):
    """Convert a plain Python value to DynamoDB's typed representation.

    ``bool`` is checked before ``int`` because ``bool`` is a subclass of ``int`` in Python and
    would otherwise serialise as a number.
    """
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, (int, float)):
        return {"N": str(value)}
    if isinstance(value, str):
        return {"S": value}
    if value is None:
        return {"NULL": True}
    if isinstance(value, dict):
        return {"M": {k: to_ddb(v) for k, v in value.items()}}
    if isinstance(value, list):
        return {"L": [to_ddb(v) for v in value]}
    raise ValueError(f"Unsupported value type for DynamoDB: {type(value)}")


def build_request(item_json, table_name, partition_key, sort_key):
    """Return (request_body, item, attribute_names) or raise ValueError with a usable message."""
    try:
        item = json.loads(item_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"item is not valid JSON: {exc}") from exc
    if not isinstance(item, dict):
        raise ValueError("item must be a JSON object at the top level")

    key_names = [partition_key] + ([sort_key] if sort_key else [])
    missing = [k for k in key_names if k not in item]
    if missing:
        raise ValueError(f"item is missing required key(s): {', '.join(missing)}")

    attributes = {k: v for k, v in item.items() if k not in key_names}
    if not attributes:
        # UpdateItem with an empty SET is a malformed request, and a payload carrying only its
        # primary key almost always means the caller templated it wrong.
        raise ValueError("item contains only the primary key; nothing to merge")

    # Attribute names are aliased because payload keys are caller-supplied and may collide with
    # DynamoDB reserved words (`status`, `size`, ...).
    names, values, assignments = {}, {}, []
    for index, (name, value) in enumerate(attributes.items()):
        names[f"#k{index}"] = name
        values[f":v{index}"] = to_ddb(value)
        assignments.append(f"#k{index} = :v{index}")

    request = {
        "TableName": table_name,
        "Key": {k: to_ddb(item[k]) for k in key_names},
        "UpdateExpression": "SET " + ", ".join(assignments),
        "ExpressionAttributeNames": names,
        "ExpressionAttributeValues": values,
    }
    return request, item, list(attributes)


def main():
    payload_path, summary_path = sys.argv[1], sys.argv[2]
    table_name = os.environ["DDB_TABLE_NAME"]
    partition_key = os.environ["DDB_PARTITION_KEY"]
    sort_key = os.environ.get("DDB_SORT_KEY") or None

    try:
        request, item, attribute_names = build_request(
            os.environ["DDB_ITEM"], table_name, partition_key, sort_key
        )
    except ValueError as exc:
        sys.exit(f"::error::{exc}")

    with open(payload_path, "w", encoding="utf-8") as handle:
        json.dump(request, handle)

    # The key, never the payload: an item body can carry values a caller would rather not publish
    # to a log, and the key alone is what you need to find the row again.
    lines = [
        "### Manifest updated",
        "",
        f"- **Table**: `{table_name}`",
        f"- **{partition_key}**: `{item[partition_key]}`",
    ]
    if sort_key:
        lines.append(f"- **{sort_key}**: `{item[sort_key]}`")
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    print(f"Merging {len(attribute_names)} attribute(s): {', '.join(attribute_names)}")


if __name__ == "__main__":
    main()
