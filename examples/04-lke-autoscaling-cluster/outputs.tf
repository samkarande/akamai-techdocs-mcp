output "cluster_id" {
  description = "ID of the LKE cluster."
  value       = linode_lke_cluster.this.id
}

output "status" {
  description = "Cluster status."
  value       = linode_lke_cluster.this.status
}

output "api_endpoints" {
  description = "Kubernetes API endpoints."
  value       = linode_lke_cluster.this.api_endpoints
}

output "dashboard_url" {
  description = "LKE dashboard URL."
  value       = linode_lke_cluster.this.dashboard_url
}

output "kubeconfig" {
  description = "Base64-encoded kubeconfig. Decode before use (see README)."
  value       = linode_lke_cluster.this.kubeconfig
  sensitive   = true
}
