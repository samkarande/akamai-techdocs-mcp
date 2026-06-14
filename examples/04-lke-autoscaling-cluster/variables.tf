variable "linode_token" {
  description = "Linode API token. Leave empty to use the LINODE_TOKEN env var."
  type        = string
  default     = ""
  sensitive   = true
}

variable "region" {
  description = "Region for the LKE cluster. us-iad is Washington, DC."
  type        = string
  default     = "us-iad"
}

variable "k8s_version" {
  description = "Kubernetes version. Confirm options with `linode-cli lke versions-list`."
  type        = string
  default     = "1.32"
}

variable "label" {
  description = "Label for the LKE cluster."
  type        = string
  default     = "example4-lke"
}

variable "node_type" {
  description = "Linode plan for worker nodes. g6-standard-2 is the Shared 4GB plan."
  type        = string
  default     = "g6-standard-2"
}

variable "desired_node_count" {
  description = "Desired/initial number of worker nodes in the pool."
  type        = number
  default     = 2
}

variable "autoscaler_min" {
  description = "Autoscaler floor (kept at the desired capacity)."
  type        = number
  default     = 2
}

variable "autoscaler_max" {
  description = "Autoscaler ceiling — the pool scales up to this under load."
  type        = number
  default     = 4
}

variable "high_availability" {
  description = "Enable the HA control plane (additional cost)."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to the cluster."
  type        = list(string)
  default     = ["example4", "lke", "managed-by-terraform"]
}
