variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Prefix used for all resource names."
  type        = string
  default     = "csv-pipeline"
}

variable "alert_email" {
  description = "Email address that receives a summary after each file is processed. Leave empty to skip."
  type        = string
  default     = ""
}
