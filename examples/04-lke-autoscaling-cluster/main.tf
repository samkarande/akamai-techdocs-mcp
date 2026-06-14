###############################################################################
# Example 4 — an autoscaling LKE (Linode Kubernetes Engine) cluster.
#
#   Kubernetes cluster in us-iad (Washington, DC) with one node pool that
#   starts at 2 nodes (desired capacity) and autoscales between 2 and N.
#
# "2 pods per node": this is NOT a node-pool / LKE setting. Standard LKE does
# not expose a kubelet --max-pods cap (the platform default is 110). Pods-per-
# node is controlled at the Kubernetes layer per workload — see
# k8s/sample-deployment.yaml, which uses topologySpreadConstraints to place at
# most 2 of its pods on each node. The README explains this in detail.
###############################################################################

resource "linode_lke_cluster" "this" {
  label       = var.label
  k8s_version = var.k8s_version
  region      = var.region
  tags        = var.tags

  pool {
    type = var.node_type

    # Desired/initial capacity. With the autoscaler enabled the live node
    # count may drift from this value as the cluster scales; that is expected.
    count = var.desired_node_count

    autoscaler {
      min = var.autoscaler_min
      max = var.autoscaler_max
    }
  }

  # Optional HA control plane.
  dynamic "control_plane" {
    for_each = var.high_availability ? [1] : []
    content {
      high_availability = true
    }
  }

  lifecycle {
    # The autoscaler owns the node count at runtime; don't fight it on apply.
    ignore_changes = [pool[0].count]
  }
}
