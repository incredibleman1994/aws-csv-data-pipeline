output "bucket_name" {
  description = "Upload CSV files to the incoming/ folder of this bucket."
  value       = aws_s3_bucket.uploads.bucket
}

output "table_name" {
  description = "DynamoDB table that stores the processed orders."
  value       = aws_dynamodb_table.orders.name
}

output "topic_arn" {
  description = "SNS topic that receives the processing summaries."
  value       = aws_sns_topic.notifications.arn
}
