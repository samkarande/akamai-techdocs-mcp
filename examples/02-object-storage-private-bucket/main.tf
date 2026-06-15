###############################################################################
# Example 2 — a private Object Storage bucket.
#
#   Bucket "raw-images" in the us-east (Newark) region, private ACL.
#
# Apply behaviour:
#   - Bucket does not exist → created, apply succeeds.
#   - Bucket already exists → skipped with an informational message,
#     apply still succeeds (no error).
#
# Destroy behaviour:
#   - Bucket is empty → deleted.
#   - Bucket is non-empty → destroy fails with a helpful message asking
#     the user to empty the bucket first. This is intentional: Terraform
#     will not silently discard objects.
#
# LINODE_TOKEN must be set in the environment (Terraform already requires
# it for the provider, so no extra steps are needed).
###############################################################################

resource "null_resource" "bucket" {
  triggers = {
    bucket_label = var.bucket_label
    region       = var.region
    acl          = var.acl
  }

  # Create the bucket, or print a helpful message if it already exists.
  provisioner "local-exec" {
    command = <<-EOT
      STATUS=$(curl -sf -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer $LINODE_TOKEN" \
        "https://api.linode.com/v4/object-storage/buckets/${var.region}/${var.bucket_label}")

      if [ "$STATUS" = "200" ]; then
        echo "INFO: Bucket '${var.bucket_label}' already exists in '${var.region}'. No changes made."
      else
        curl -sf -X POST \
          -H "Authorization: Bearer $LINODE_TOKEN" \
          -H "Content-Type: application/json" \
          -d '{"label":"${var.bucket_label}","region":"${var.region}","acl":"${var.acl}","cors_enabled":false}' \
          "https://api.linode.com/v4/object-storage/buckets" > /dev/null \
          || { echo "ERROR: Failed to create bucket '${var.bucket_label}'."; exit 1; }
        echo "INFO: Bucket '${var.bucket_label}' created in '${var.region}'."
      fi
    EOT
  }

  # Delete the bucket on destroy — fails if non-empty (intentional safety guard).
  provisioner "local-exec" {
    when = destroy
    command = <<-EOT
      STATUS=$(curl -sf -X DELETE \
        -H "Authorization: Bearer $LINODE_TOKEN" \
        -o /dev/null -w '%{http_code}' \
        "https://api.linode.com/v4/object-storage/buckets/${self.triggers.region}/${self.triggers.bucket_label}")

      if [ "$STATUS" = "200" ] || [ "$STATUS" = "204" ]; then
        echo "INFO: Bucket '${self.triggers.bucket_label}' deleted."
      else
        echo "ERROR: Could not delete bucket '${self.triggers.bucket_label}'."
        echo "       If it contains objects, empty it first then re-run terraform destroy."
        exit 1
      fi
    EOT
  }
}

locals {
  bucket_hostname = "${var.bucket_label}.${var.region}.linodeobjects.com"
}
