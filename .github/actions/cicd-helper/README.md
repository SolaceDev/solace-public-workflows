
# cicd-helper GitHub Action Usage Guide


The `cicd-helper` GitHub Action is a reusable utility for CI/CD pipelines to automate Slack notifications and DynamoDB operations. The action's behavior is controlled by the `rc_step` input, which selects the operation mode.

---

## Usage

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: <step_name>
    # ...other required inputs for the step...
```

---

## Inputs

| Name                   | Required | Description                                                                                   |
|------------------------|----------|-----------------------------------------------------------------------------------------------|
| `rc_step`              | Yes      | The operation mode to run. See supported steps below.                                         |
| `slack_token`          | Sometimes| Slack API token (required for Slack steps; not required for DynamoDB steps).                  |
| `slack_channel`        | Sometimes| Slack channel ID or name (required for Slack steps).                                          |
| `message_header`       | Sometimes| Header for changelog message (for `prepare_change_log_message`).                             |
| `repo_name`            | Sometimes| GitHub repository (e.g., `org/repo`) (for `prepare_change_log_message`).                     |
| `deployed_ref`         | Sometimes| Deployed reference SHA or tag (for `prepare_change_log_message`, e.g., previous deployment, base branch, or environment). |
| `candidate_ref`        | Sometimes| Candidate reference SHA or tag (for `prepare_change_log_message`, e.g., new deployment, PR head, or target commit).         |
| `contributors_raw_list`| Optional | Comma-separated contributor emails (for `prepare_change_log_message`). If omitted, contributor info will be queried via GitHub. |
| `message`              | Sometimes| Message text (for `post_to_channel`).                                                         |
| `thread_ts`            | Sometimes| Slack thread timestamp (for thread operations).                                               |
| `thread_message`       | Sometimes| Message text for thread (for `post_to_thread`).                                               |
| `previous_message`     | Optional | Previous message text (for `update_message_header`). If omitted, the action will deduce it from `thread_ts`. |
| `new_message_header`   | Sometimes| New header text (for `update_message_header`).                                                |
| `thread_message_ts`    | Sometimes| Timestamp of the message to update (for `update_thread_message`).                             |
| `new_thread_message`   | Sometimes| New message text to replace an existing thread reply (for `update_thread_message`).          |
| `thread_message_ts`    | Sometimes| Timestamp of the message to update in thread (for `update_thread_message`).                  |
| `ddb_item_to_be_added` | Sometimes| JSON string of the item (for `add_item_from_json_to_dynamodb_table`).                        |
| `ddb_table_name`       | Sometimes| DynamoDB table name (for DynamoDB steps).                                                     |
| `ddb_partition_key`    | Sometimes| Partition key name (for DynamoDB steps).                                                      |
| `ddb_sort_key`         | Optional | Sort key name (for `add_item_from_json_to_dynamodb_table`).                                   |
| `ddb_query_json`       | Sometimes| JSON string for the query (for `item_exists_in_dynamodb`).                                    |
| `ddb_exists_output`    | Optional | Output variable name (default: `ITEM_EXISTS`) (for `item_exists_in_dynamodb`).                |
| `ddb_field_path`       | Sometimes| Dot-separated path to the field (for `get_item_value_from_dynamodb`).                         |
| `ddb_output_name`      | Optional | Output variable name (default: `FIELD_VALUE`) (for `get_item_value_from_dynamodb`).           |
| `ddb_return_section`   | Optional | If set to `true`, returns the entire section as clean JSON (for `get_item_value_from_dynamodb`).|
| `ddb_table_index_name` | Sometimes| DynamoDB table's index name (for `get_item_by_index`).                                        |
| `ddb_index_field_name` | Sometimes| DynamoDB table field used for index (for `get_item_by_index`).                                |
| `ddb_index_field_value`| Sometimes| DynamoDB table, value used to match index field value (for `get_item_by_index`).             |

> **Note:** Not all inputs are required for every step. See the table below for step-specific requirements.

---

## Supported rc_step Modes

| rc_step                        | Description                                               | Required Inputs                                                                                      | Outputs                                 |
|--------------------------------|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------|-----------------------------------------|
| `prepare_change_log_message`    | Prepares a formatted changelog message for Slack. Suitable for any deployment environment (not just release candidates). | `repo_name`, `message_header`, `deployed_ref`, `candidate_ref`, (`contributors_raw_list` optional), `slack_token` | `CHANGE_LOG_MESSAGE`                    |
| `post_to_channel`              | Posts a message to a Slack channel.                       | `slack_channel`, `message`, `slack_token`                                                            | `MAIN_SLACK_THREAD_TS`, `MAIN_SLACK_MESSAGE` |
| `update_message_header`        | Updates the header of a Slack message in a thread.        | `slack_channel`, `thread_ts`, `new_message_header`, `slack_token`, (`previous_message` optional; deduced from `thread_ts` if omitted) |                                         |
| `post_to_thread`               | Posts a message to a Slack thread.                        | `slack_channel`, `thread_message`, `thread_ts`, `slack_token`                                        | `THREAD_MESSAGE_TS`                     |
| `update_thread_message`        | Updates a message in a Slack thread.                      | `slack_channel`, `thread_message_ts`, `new_thread_message`, `slack_token`                            |                                         |
| `add_item_from_json_to_dynamodb_table` | Adds an item to a DynamoDB table from a JSON string. | `ddb_item_to_be_added`, `ddb_table_name`, `ddb_partition_key`, (`ddb_sort_key` optional)             |                                         |
| `item_exists_in_dynamodb`      | Checks if an item exists in a DynamoDB table.             | `ddb_query_json`, `ddb_table_name`, `ddb_partition_key`, (`ddb_exists_output` optional)              | `ITEM_EXISTS` (or custom name)          |
| `get_item_value_from_dynamodb` | Retrieves a specific field value or section from a DynamoDB item. | `ddb_query_json`, `ddb_table_name`, `ddb_partition_key`, (`ddb_sort_key` optional), `ddb_field_path`, (`ddb_output_name` optional), (`ddb_return_section` optional) | Field value or section as output        |
| `get_item_by_index`            | Retrieves an item from a DynamoDB table using a secondary index with optional JSON query filters. | `ddb_table_name`, `ddb_table_index_name`, `ddb_index_field_name`, `ddb_index_field_value`, `ddb_query_json`, (`ddb_output_name` optional) | Index item data as output               |

---

## Outputs

- Outputs are set as GitHub Actions outputs and can be referenced as `${{ steps.<step_id>.outputs.<output_name> }}`.
- See the table above for which steps produce outputs.

---

## Example Usage


### Prepare and Post a Changelog Message to Slack

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: prepare_change_log_message
    slack_token: ${{ secrets.SLACK_TOKEN }}
    repo_name: ${{ github.repository }}
    message_header: ":loading: Starting Deployment"
    deployed_ref: ${{ steps.gather_info.outputs.DEPLOYED_REF }}
    candidate_ref: ${{ steps.gather_info.outputs.CANDIDATE_REF }}
    contributors_raw_list: ${{ steps.gather_info.outputs.CONTRIBUTORS_RAW_LIST }}

  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: post_to_channel
    slack_token: ${{ secrets.SLACK_TOKEN }}
    slack_channel: ${{ env.SLACK_CHANNEL }}
    message: ${{ steps.prepare_change_log.outputs.CHANGE_LOG_MESSAGE }}
```

### Update the Header of a Slack Message in a Thread

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: update_message_header
    slack_token: ${{ secrets.SLACK_TOKEN }}
    slack_channel: ${{ env.SLACK_CHANNEL }}
    thread_ts: ${{ needs.pre-deployment-checks.outputs.MAIN_SLACK_THREAD_TS }}
    new_message_header: ${{ steps.status.outputs.message_header }}
    # previous_message: ${{ needs.pre-deployment-checks.outputs.MAIN_SLACK_MESSAGE }} # Optional, will be deduced from thread_ts if omitted
```

### Post a Message to a Slack Thread

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: post_to_thread
    slack_token: ${{ secrets.SLACK_TOKEN }}
    slack_channel: ${{ env.SLACK_CHANNEL }}
    thread_ts: ${{ steps.send_changelog.outputs.MAIN_SLACK_THREAD_TS }}
    thread_message: ":white_check_mark: Job completed successfully."
```

### Update a Message in a Slack Thread

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: update_thread_message
    slack_token: ${{ secrets.SLACK_TOKEN }}
    slack_channel: ${{ env.SLACK_CHANNEL }}
    thread_message_ts: ${{ steps.some_step.outputs.THREAD_MESSAGE_TS }}
    new_thread_message: "Updated message text."
```

### Add an Item to DynamoDB

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: add_item_from_json_to_dynamodb_table
    ddb_item_to_be_added: '{"id": "123", "status": "done"}'
    ddb_table_name: "my-table"
    ddb_partition_key: "id"
    # ddb_sort_key: "timestamp" # Optional
```

### Check if an Item Exists in DynamoDB (with optional sort key)

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: item_exists_in_dynamodb
    ddb_query_json: '{"id": "123", "timestamp": "2024-01-01T00:00:00Z"}'
    ddb_table_name: "my-table"
    ddb_partition_key: "id"
    ddb_sort_key: "timestamp" # Optional, for composite key tables
    ddb_exists_output: ITEM_EXISTS
```

### Get a Field Value or Section from DynamoDB

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: get_item_value_from_dynamodb
    ddb_query_json: '{"squad": "ai", "repository": "solace-agent-mesh-enterprise"}'
    ddb_table_name: "solace-cloud-manifest"
    ddb_partition_key: "squad"
    ddb_field_path: "dev.image_tag"
    ddb_output_name: DEV_IMAGE_TAG
    ddb_return_section: false # or omit for single value
```

To get the entire `dev` section as JSON:

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: get_item_value_from_dynamodb
    ddb_query_json: '{"squad": "ai", "repository": "solace-agent-mesh-enterprise"}'
    ddb_table_name: "solace-cloud-manifest"
    ddb_partition_key: "squad"
    ddb_field_path: "dev"
    ddb_output_name: DEV_SECTION
    ddb_return_section: true
```

**Outputs:**

- If `ddb_return_section` is `false` or omitted: the value of the field (e.g., `0.0.6-1560dda3fb`)
- If `ddb_return_section` is `true`: the entire section as compact JSON (e.g., `{ "chart_version": "", "image_tag": "0.0.6-1560dda3fb", ... }`)
- If no item is found: `NOT_FOUND`
- If the field/section is not found: `FIELD_NOT_FOUND`


### Get an Item by Index from DynamoDB

```yaml
- name: Fetch SHA information from ebp-build-manifest
  id: fetch_headsha_manifest_entry
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: get_item_by_index
    aws_region: ca-central-1
    ddb_table_name: "ebp-build-manifest"
    ddb_table_index_name: "ebp-build-manifest-sha"
    ddb_index_field_name: "git_sha"
    ddb_index_field_value: "${{ env.HEAD_SHA }}"
    ddb_output_name: "mq_sha_metadata"
    ddb_query_json: >-
      {
        "metadata": {
          "merge_queue": "true"
        }
      }
```

**Description:**
This step queries the `ebp-build-manifest` table using the `ebp-build-manifest-sha` index to find items where the `git_sha` field matches `${{ env.HEAD_SHA }}`. It also applies additional filters from the JSON query to only return items where `metadata.merge_queue` equals `"true"`.

**Outputs:**
- If an item is found: the complete item data as JSON
- If no item is found: `NOT_FOUND`


### Check if an Item Exists in DynamoDB

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/cicd-helper@main
  with:
    rc_step: item_exists_in_dynamodb
    ddb_query_json: '{"id": "123"}'
    ddb_table_name: "my-table"
    ddb_partition_key: "id"
    ddb_exists_output: ITEM_EXISTS
```

---

**Note:**
- For Slack operations, `slack_token` must be provided.
- For DynamoDB operations, `slack_token` is not required. Ensure AWS credentials are available in the environment (via secrets or IAM role).
