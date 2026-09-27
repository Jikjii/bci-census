output "function_name" {
  description = "The Lambda function."
  value       = aws_lambda_function.wire.function_name
}

output "state_table" {
  description = "The DynamoDB table holding what the Wire has seen."
  value       = aws_dynamodb_table.state.name
}

output "send_test_alert" {
  description = "Run this to send one test alert through the deployed function."
  value       = "aws lambda invoke --region ${var.region} --function-name ${aws_lambda_function.wire.function_name} --cli-binary-format raw-in-base64-out --payload '{\"test\":true}' /dev/stdout"
}

output "check_sources" {
  description = "Run this to see when each source last ran and any errors."
  value       = "aws lambda invoke --region ${var.region} --function-name ${aws_lambda_function.wire.function_name} --cli-binary-format raw-in-base64-out --payload '{\"status\":true}' /dev/stdout"
}

output "follow_logs" {
  description = "Run this to watch each minute's run."
  value       = "aws logs tail ${aws_cloudwatch_log_group.wire.name} --region ${var.region} --follow"
}

output "ntfy_subscribe_url" {
  description = "Subscribe to this in the ntfy app (only when ntfy_enabled). Anyone with it can read your alerts."
  value       = var.ntfy_enabled ? "${trimsuffix(var.ntfy_server, "/")}/${local.ntfy_topic}" : ""
  sensitive   = true
}
