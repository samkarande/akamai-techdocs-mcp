variable "linode_token" {
  description = "Linode API token. Leave empty to use the LINODE_TOKEN env var."
  type        = string
  default     = ""
  sensitive   = true
}

variable "region" {
  description = <<-EOT
    Object Storage region. "us-east" is Newark, NJ — the location historically
    addressed as the "us-east-1" Object Storage cluster. Confirm available
    regions with `linode-cli object-storage endpoints` (or `regions list`).
  EOT
  type        = string
  default     = "us-east"
}

variable "bucket_label" {
  description = "Bucket name. Must be DNS-compatible: 3-63 chars, lowercase."
  type        = string
  default     = "raw-images"
}

variable "acl" {
  description = "Canned ACL. 'private' keeps the bucket non-public."
  type        = string
  default     = "private"

  validation {
    condition     = contains(["private", "public-read", "authenticated-read", "public-read-write"], var.acl)
    error_message = "acl must be one of: private, public-read, authenticated-read, public-read-write."
  }
}
