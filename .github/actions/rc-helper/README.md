# rc-helper GitHub Action Usage Guide

The `rc-helper` GitHub Action is a reusable utility for CI/CD pipelines to automate Slack notifications and DynamoDB operations. The action's behavior is controlled by the `rc_step` input, which selects the operation mode.

---

## Usage

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/rc-helper@main
  with:
    rc_step: <step_name>
    # ...other required inputs for the step...
```

---

## Inputs

| Name                   | Required | Description                                                                                   |
|------------------------|----------|-----------------------------------------------------------------------------------------------|
| `rc_step`              | Yes      | The operation mode to run. See supported steps below.                                         |
| `slack_token`          | Sometimes| Slack API token (required for Slack steps).                                                   |
| `slack_channel`        | Sometimes| Slack channel ID or name (required for Slack steps).                                          |
| `message_header`       | Sometimes| Header for changelog message (for `prepare_change_log_message`).                             |
| `repo_name`            | Sometimes| GitHub repository (e.g., `org/repo`) (for `prepare_change_log_message`).                     |
| `deployed_ref`         | Sometimes| Deployed reference SHA or tag (for `prepare_change_log_message`, e.g., previous deployment, base branch, or environment). |
| `candidate_ref`        | Sometimes| Candidate reference SHA or tag (for `prepare_change_log_message`, e.g., new deployment, PR head, or target commit).         |
| `contributors_raw_list`| Sometimes| Comma-separated contributor emails (for `prepare_change_log_message`).                        |
| `message`              | Sometimes| Message text (for `post_to_channel`).                                                         |
| `thread_ts`            | Sometimes| Slack thread timestamp (for thread operations).                                               |
| `thread_message`       | Sometimes| Message text for thread (for `post_to_thread`).                                               |
| `previous_message`     | Sometimes| Previous message text (for `update_message_header`).                                          |
| `new_message_header`   | Sometimes| New header text (for `update_message_header`).                                                |
| `thread_message_ts`    | Sometimes| Timestamp of the message to update (for `update_thread_message`).                             |
| `new_thread_message`   | Sometimes| New message text (for `update_thread_message`).                                               |
| `ddb_item_to_be_added` | Sometimes| JSON string of the item (for `add_item_from_json_to_dynamodb_table`).                        |
| `ddb_table_name`       | Sometimes| DynamoDB table name (for DynamoDB steps).                                                     |
| `ddb_partition_key`    | Sometimes| Partition key name (for DynamoDB steps).                                                      |
| `ddb_sort_key`         | Optional | Sort key name (for `add_item_from_json_to_dynamodb_table`).                                   |
| `ddb_query_json`       | Sometimes| JSON string for the query (for `item_exists_in_dynamodb`).                                    |
| `ddb_exists_output`    | Optional | Output variable name (default: `ITEM_EXISTS`) (for `item_exists_in_dynamodb`).                |

> **Note:** Not all inputs are required for every step. See the table below for step-specific requirements.

---

## Supported rc_step Modes

| rc_step                        | Description                                               | Required Inputs                                                                                      | Outputs                                 |
|--------------------------------|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------|-----------------------------------------|
| `prepare_change_log_message`    | Prepares a formatted changelog message for Slack. Suitable for any deployment environment (not just release candidates). | `repo_name`, `message_header`, `deployed_ref`, `candidate_ref`, `contributors_raw_list`, `slack_token` | `CHANGE_LOG_MESSAGE`                    |
| `post_to_channel`              | Posts a message to a Slack channel.                       | `slack_channel`, `message`, `slack_token`                                                            | `MAIN_SLACK_THREAD_TS`, `MAIN_SLACK_MESSAGE` |
| `update_message_header`        | Updates the header of a Slack message in a thread.        | `slack_channel`, `thread_ts`, `previous_message`, `new_message_header`, `slack_token`                |                                         |
| `post_to_thread`               | Posts a message to a Slack thread.                        | `slack_channel`, `thread_message`, `thread_ts`, `slack_token`                                        | `THREAD_MESSAGE_TS`                     |
| `update_thread_message`        | Updates a message in a Slack thread.                      | `slack_channel`, `thread_message_ts`, `new_thread_message`, `slack_token`                            |                                         |
| `add_item_from_json_to_dynamodb_table` | Adds an item to a DynamoDB table from a JSON string. | `ddb_item_to_be_added`, `ddb_table_name`, `ddb_partition_key`, (`ddb_sort_key` optional)             |                                         |
| `item_exists_in_dynamodb`      | Checks if an item exists in a DynamoDB table.             | `ddb_query_json`, `ddb_table_name`, `ddb_partition_key`, (`ddb_exists_output` optional)              | `ITEM_EXISTS` (or custom name)          |

---

## Outputs

- Outputs are set as GitHub Actions outputs and can be referenced as `${{ steps.<step_id>.outputs.<output_name> }}`.
- See the table above for which steps produce outputs.

---

## Example Usage


### Prepare and Post a Changelog Message to Slack

```yaml
- name: Prepare Change Log
  uses: SolaceDev/solace-public-workflows/.github/actions/rc-helper@main
  with:
    rc_step: prepare_change_log_message
    slack_token: ${{ secrets.SLACK_TOKEN }}
    repo_name: ${{ github.repository }}
    message_header: ":loading: Starting Deployment"
    deployed_ref: ${{ steps.gather_info.outputs.DEPLOYED_REF }}
    candidate_ref: ${{ steps.gather_info.outputs.CANDIDATE_REF }}
    contributors_raw_list: ${{ steps.gather_info.outputs.CONTRIBUTORS_RAW_LIST }}

  uses: SolaceDev/solace-public-workflows/.github/actions/rc-helper@main
  with:
    rc_step: post_to_channel
    slack_token: ${{ secrets.SLACK_TOKEN }}
    slack_channel: ${{ env.SLACK_CHANNEL }}
    message: ${{ steps.prepare_change_log.outputs.CHANGE_LOG_MESSAGE }}
```

### Update the Header of a Slack Message in a Thread

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/rc-helper@main
  with:
    rc_step: update_message_header
    slack_token: ${{ secrets.SLACK_TOKEN }}
    slack_channel: ${{ env.SLACK_CHANNEL }}
    thread_ts: ${{ needs.pre-deployment-checks.outputs.MAIN_SLACK_THREAD_TS }}
    previous_message: ${{ needs.pre-deployment-checks.outputs.MAIN_SLACK_MESSAGE }}
    new_message_header: ${{ steps.status.outputs.message_header }}
```

### Post a Message to a Slack Thread

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/rc-helper@main
  with:
    rc_step: post_to_thread
    slack_token: ${{ secrets.SLACK_TOKEN }}
    slack_channel: ${{ env.SLACK_CHANNEL }}
    thread_ts: ${{ steps.send_changelog.outputs.MAIN_SLACK_THREAD_TS }}
    thread_message: ":white_check_mark: Job completed successfully."
```

### Update a Message in a Slack Thread

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/rc-helper@main
  with:
    rc_step: update_thread_message
    slack_token: ${{ secrets.SLACK_TOKEN }}
    slack_channel: ${{ env.SLACK_CHANNEL }}
    thread_message_ts: ${{ steps.some_step.outputs.THREAD_MESSAGE_TS }}
    new_thread_message: "Updated message text."
```

### Add an Item to DynamoDB

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/rc-helper@main
  with:
    rc_step: add_item_from_json_to_dynamodb_table
    ddb_item_to_be_added: '{"id": "123", "status": "done"}'
    ddb_table_name: "my-table"
    ddb_partition_key: "id"
    # ddb_sort_key: "timestamp" # Optional
```

### Check if an Item Exists in DynamoDB

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/rc-helper@main
  with:
    rc_step: item_exists_in_dynamodb
    ddb_query_json: '{"id": "123"}'
    ddb_table_name: "my-table"
    ddb_partition_key: "id"
    ddb_exists_output: ITEM_EXISTS
```

---

**Note:**  
- For all Slack operations, `slack_token` must be provided.  
- For DynamoDB operations, ensure AWS credentials are available in the environment (via secrets or IAM role).
