###############################################################################
# Example 2 — a private Object Storage bucket.
#
#   Bucket "raw-images" in the us-east (Newark / "us-east-1") region,
#   with a private ACL so its objects are not publicly readable.
###############################################################################

resource "linode_object_storage_bucket" "raw_images" {
  region = var.region
  label  = var.bucket_label

  # "private" => objects are not publicly accessible. This is the key setting
  # for "make the object store non public". The canned ACL here is applied at
  # bucket creation via the Linode API, so no S3 access keys are required.
  acl = var.acl

  # Defense in depth: disable cross-origin sharing.
  cors_enabled = false

  # NOTE: `versioning` and `lifecycle_rule` are managed over the S3 API and
  # would require `access_key`/`secret_key` (e.g. from a
  # linode_object_storage_key) on this resource, so they're omitted here to
  # keep the example token-only.
}
