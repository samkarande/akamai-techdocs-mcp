###############################################################################
# Example 3 — a Linode Managed MySQL database (DBaaS).
#
#   MySQL 8 in the us-east (Newark / "us-east-1") region on the Shared 4GB
#   plan. Uses linode_database_mysql_v2 (the current Aiven-backed managed
#   database; the legacy linode_database_mysql resource is being retired).
#
# Storage note: managed-database storage is bundled with the node plan and is
# not configured separately, so "4GB" is expressed by choosing the 4GB plan
# (g6-standard-2). Pick a larger plan if you need more capacity.
###############################################################################

resource "linode_database_mysql_v2" "this" {
  label     = var.label
  engine_id = var.engine
  region    = var.region
  type      = var.database_type

  # 1 = single node; set to 3 for a high-availability cluster.
  cluster_size = var.cluster_size

  # Only these IPs/CIDRs may connect. Empty = no inbound access.
  allow_list = var.allow_list
}
