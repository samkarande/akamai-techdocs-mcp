###############################################################################
# Example 4 — LKE autoscaling cluster with Apache + Nginx workloads.
#
# Topology:
#   LKE cluster (us-iad-2, g6-standard-1 nodes, autoscale 2–4)
#    ├─ node-1: 1 Apache pod + 1 Nginx pod  (2 pods/node)
#    └─ node-2: 1 Apache pod + 1 Nginx pod  (2 pods/node)
#   NodeBalancer (apache-svc, port 80) ──> Apache pods
#   NodeBalancer (nginx-svc,  port 80) ──> Nginx pods
#   Firewall: TCP 80/443 open to internet; NodePort range open to Linode
#             private network so NodeBalancers can reach the pods.
#
# Each pod serves a static HTML page showing server name, version,
# pod name, and pod IP — generated at container start-up via shell.
#
# Prerequisites:
#   - kubectl must be installed on the machine running Terraform.
#   - LINODE_TOKEN must be set in the environment.
###############################################################################

resource "linode_lke_cluster" "this" {
  label       = var.label
  k8s_version = var.k8s_version
  region      = var.region
  tags        = var.tags

  pool {
    type  = var.node_type
    count = var.desired_node_count

    autoscaler {
      min = var.autoscaler_min
      max = var.autoscaler_max
    }
  }

  dynamic "control_plane" {
    for_each = var.high_availability ? [1] : []
    content {
      high_availability = true
    }
  }

  lifecycle {
    ignore_changes = [pool[0].count]
  }
}

# --- Firewall ----------------------------------------------------------------

resource "linode_firewall" "lke" {
  label = "${var.label}-fw"
  tags  = var.tags

  inbound_policy  = "DROP"
  outbound_policy = "ACCEPT"

  inbound {
    label    = "allow-http"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "80"
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  inbound {
    label    = "allow-https"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "443"
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  # NodeBalancers reach LKE nodes over the Linode private network on the
  # Kubernetes NodePort range. Without this rule, LoadBalancer services
  # will not receive traffic from the NodeBalancer.
  inbound {
    label    = "allow-nodeport-private"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "30000-32767"
    ipv4     = ["192.168.0.0/16"]
  }

  linodes = [for node in linode_lke_cluster.this.pool[0].nodes : node.instance_id]
}

# --- Kubeconfig --------------------------------------------------------------

resource "local_file" "kubeconfig" {
  content         = base64decode(linode_lke_cluster.this.kubeconfig)
  filename        = "${path.module}/kubeconfig.yaml"
  file_permission = "0600"
}

# --- Kubernetes workloads ----------------------------------------------------

resource "null_resource" "k8s_workloads" {
  depends_on = [local_file.kubeconfig]

  triggers = {
    cluster_id    = linode_lke_cluster.this.id
    manifests_md5 = md5(join("", [
      file("${path.module}/k8s/apache.yaml"),
      file("${path.module}/k8s/nginx.yaml"),
    ]))
  }

  provisioner "local-exec" {
    command = <<-EOT
      echo "Waiting for LKE API server to be reachable (timeout 5 min)..."
      TIMEOUT=300
      ELAPSED=0
      until kubectl --kubeconfig=${local_file.kubeconfig.filename} cluster-info --request-timeout=5s >/dev/null 2>&1; do
        if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
          echo ""
          echo "WARNING: LKE API not reachable after $${TIMEOUT}s."
          echo "The cluster API endpoint may only be accessible from within Linode's network."
          echo "Apply the manifests manually once the cluster is ready:"
          echo ""
          echo "  kubectl --kubeconfig=${local_file.kubeconfig.filename} apply --validate=false -f ${path.module}/k8s/"
          echo ""
          exit 0
        fi
        echo "  Not ready yet ($${ELAPSED}s elapsed), retrying in 15s..."
        sleep 15
        ELAPSED=$((ELAPSED + 15))
      done
      echo "API ready. Applying manifests..."
      kubectl --kubeconfig=${local_file.kubeconfig.filename} apply --validate=false -f ${path.module}/k8s/
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = "kubectl --kubeconfig=${path.module}/kubeconfig.yaml delete -f ${path.module}/k8s/ --ignore-not-found || true"
  }
}
