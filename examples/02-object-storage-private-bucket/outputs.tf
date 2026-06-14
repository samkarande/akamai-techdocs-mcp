output "bucket_label" {
  description = "The bucket name."
  value       = linode_object_storage_bucket.raw_images.label
}

output "bucket_region" {
  description = "Region the bucket was created in."
  value       = linode_object_storage_bucket.raw_images.region
}

output "bucket_hostname" {
  description = "S3-compatible hostname for the bucket."
  value       = linode_object_storage_bucket.raw_images.hostname
}

output "bucket_acl" {
  description = "Effective canned ACL (private = non-public)."
  value       = linode_object_storage_bucket.raw_images.acl
}
