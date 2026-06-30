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
  description = "Base64-encoded kubeconfig. Decode before use (see kubeconfig_path)."
  value       = linode_lke_cluster.this.kubeconfig
  sensitive   = true
}

output "kubeconfig_path" {
  description = "Path to the decoded kubeconfig written by Terraform."
  value       = local_file.kubeconfig.filename
}

output "firewall_id" {
  description = "ID of the firewall attached to LKE nodes."
  value       = linode_firewall.lke.id
}

output "get_service_ips" {
  description = "Run this command to see the NodeBalancer IPs assigned to each service."
  value       = "kubectl --kubeconfig=${local_file.kubeconfig.filename} get svc apache nginx -o wide"
}
