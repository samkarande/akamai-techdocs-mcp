terraform {
  required_version = ">= 1.5.0"

  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 2.13"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "linode" {
  # Token is read from var.linode_token, or from the LINODE_TOKEN env var
  # if you leave the variable unset.
  token = var.linode_token != "" ? var.linode_token : null
}
