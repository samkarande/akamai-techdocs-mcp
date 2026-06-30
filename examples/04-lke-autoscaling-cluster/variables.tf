variable "linode_token" {
  description = "Linode API token. Leave empty to use the LINODE_TOKEN env var."
  type        = string
  default     = ""
  sensitive   = true
}

variable "region" {
  description = "Linode region. us-iad-2 is Washington DC (secondary AZ)."
  type        = string
  default     = "us-iad-2"
}

variable "k8s_version" {
  description = "Kubernetes version. Check available versions with `linode-cli lke versions-list` or the Linode API."
  type        = string
  default     = "1.35"
}

variable "label" {
  description = "Label prefix for the LKE cluster and firewall."
  type        = string
  default     = "example4-lke"
}

variable "node_type" {
  description = "Linode plan for worker nodes. g6-standard-1 is the Shared 2 GB plan."
  type        = string
  default     = "g6-standard-1"
}

variable "desired_node_count" {
  description = "Desired/initial number of worker nodes in the pool."
  type        = number
  default     = 2
}

variable "autoscaler_min" {
  description = "Autoscaler floor — minimum number of nodes."
  type        = number
  default     = 2
}

variable "autoscaler_max" {
  description = "Autoscaler ceiling — maximum number of nodes under load."
  type        = number
  default     = 4
}

variable "high_availability" {
  description = "Enable the HA control plane (additional cost)."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to the cluster and firewall."
  type        = list(string)
  default     = ["example4", "lke", "managed-by-terraform"]
}
