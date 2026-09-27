# The Wire on AWS: one small Lambda woken every minute by EventBridge, remembering what it has
# seen in DynamoDB. Expected cost is about $1 a month; the budget below emails you well before
# anything surprising happens.

locals {
  repo = abspath("${path.module}/../..")

  # Only what the Lambda runs: the two packages (standard library only, nothing to install)
  # and the census the alerts quote when the site can't be reached.
  package_files = sort(tolist(setunion(
    fileset(local.repo, "wire/**/*.py"),
    fileset(local.repo, "census/**/*.py"),
    toset(["data/latest/census.json", "data/latest/curated.json"]),
  )))

  ntfy_topic = !var.ntfy_enabled ? "" : (
    var.ntfy_topic != "" ? var.ntfy_topic : "bci-wire-${random_password.ntfy_topic[0].result}"
  )

  environment = merge(
    {
      WIRE_TABLE            = aws_dynamodb_table.state.name
      SEC_USER_AGENT        = var.sec_user_agent
      TELEGRAM_BOT_TOKEN    = var.telegram_bot_token
      TELEGRAM_CHAT_ID      = var.telegram_chat_id
      NTFY_SERVER           = var.ntfy_server
      NTFY_TOPIC            = local.ntfy_topic
      NTFY_TOKEN            = var.ntfy_token
      WIRE_TZ               = var.timezone
      WIRE_QUIET_HOURS      = var.quiet_hours
      WIRE_QUIET_URGENT     = var.quiet_urgent ? "true" : "false"
      WIRE_DIGEST_HOURS     = join(",", [for h in var.digest_hours : tostring(h)])
      CENSUS_SITE_URL       = var.site_url
      OPENFDA_API_KEY       = var.openfda_api_key
      WIRE_TIME_BUDGET_S    = tostring(var.timeout_seconds - 30)
      WIRE_DISABLED_SOURCES = join(",", var.disabled_sources)
      WIRE_JOB_BOARDS       = length(var.job_boards) > 0 ? jsonencode(var.job_boards) : ""
    },
    var.extra_environment,
  )
}

# --- code --------------------------------------------------------------------

data "archive_file" "wire" {
  type        = "zip"
  output_path = "${path.module}/build/wire.zip"

  dynamic "source" {
    for_each = local.package_files
    content {
      filename = source.value
      content  = file("${local.repo}/${source.value}")
    }
  }
}

resource "random_password" "ntfy_topic" {
  count   = var.ntfy_enabled && var.ntfy_topic == "" ? 1 : 0
  length  = 24
  special = false
  upper   = false
}

# --- state -------------------------------------------------------------------

resource "aws_dynamodb_table" "state" {
  name         = "${var.name}-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# --- permissions: read and write its own table, write its own logs, nothing else ---

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "wire" {
  name               = "${var.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "wire" {
  statement {
    sid       = "State"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.state.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.wire.arn}:*"]
  }
}

resource "aws_iam_role_policy" "wire" {
  name   = "${var.name}-access"
  role   = aws_iam_role.wire.id
  policy = data.aws_iam_policy_document.wire.json
}

# --- the function --------------------------------------------------------------

resource "aws_cloudwatch_log_group" "wire" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "wire" {
  function_name    = var.name
  description      = "BCI Wire: polls primary sources and pushes new BCI news with a draft post"
  role             = aws_iam_role.wire.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "wire.lambda_handler.handler"
  filename         = data.archive_file.wire.output_path
  source_code_hash = data.archive_file.wire.output_base64sha256
  memory_size      = var.memory_mb
  timeout          = var.timeout_seconds

  environment {
    # Empty settings are left out so the Wire's own defaults apply.
    variables = { for k, v in local.environment : k => v if v != "" }
  }

  depends_on = [aws_cloudwatch_log_group.wire, aws_iam_role_policy.wire]

  lifecycle {
    precondition {
      condition     = (var.telegram_bot_token != "" && var.telegram_chat_id != "") || var.ntfy_enabled
      error_message = "Alerts need somewhere to go: set telegram_bot_token and telegram_chat_id (see README), or ntfy_enabled = true."
    }
  }
}

# A missed minute is simply picked up by the next one, so failed runs are never retried.
resource "aws_lambda_function_event_invoke_config" "wire" {
  function_name                = aws_lambda_function.wire.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 60
}

# --- the clock -------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.name}-schedule"
  description         = "Wakes the BCI Wire; each source keeps its own interval"
  schedule_expression = var.schedule
  state               = var.paused ? "DISABLED" : "ENABLED"
}

resource "aws_cloudwatch_event_target" "wire" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "wire"
  arn       = aws_lambda_function.wire.arn
  input     = jsonencode({ source = "schedule" })
}

resource "aws_lambda_permission" "schedule" {
  statement_id  = "AllowEventBridgeSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.wire.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

# --- cost guardrail ----------------------------------------------------------------

resource "aws_budgets_budget" "account" {
  count        = var.budget_email == "" ? 0 : 1
  name         = "${var.name}-account-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }
}
