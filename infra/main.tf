# The AWS side of the site (docs/cloud.md). Neon is set up by hand, and the
# secrets go into SSM Parameter Store by hand too, never through Terraform -
# anything Terraform creates is written, in full, into its state.

terraform {
  # use_lockfile (S3-native state locking, no DynamoDB table) needs 1.10.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # The state lives in a bucket created once by hand (versioned, private),
  # not in git. The lock file next to it stops two applies running at once.
  # The bucket's name holds the account id, so it comes from the gitignored
  # backend.hcl: terraform init -backend-config=backend.hcl
  backend "s3" {
    key          = "infra/terraform.tfstate"
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
  }
}

# The account's project is pinned to eu-north-1; its guardrails block other regions.
provider "aws" {
  region = "eu-north-1"

  default_tags {
    tags = {
      Project = "il-vacation-budget"
    }
  }
}
