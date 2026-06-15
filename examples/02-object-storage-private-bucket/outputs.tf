output "bucket_label" {
  description = "The bucket name."
  value       = var.bucket_label
}

output "bucket_region" {
  description = "Region the bucket lives in."
  value       = var.region
}

output "bucket_hostname" {
  description = "S3-compatible hostname for the bucket."
  value       = local.bucket_hostname
}

output "bucket_acl" {
  description = "Canned ACL applied at creation (private = non-public)."
  value       = var.acl
}
