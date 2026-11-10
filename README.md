# Sentinel Split Architecture

Proof-of-concept AWS infrastructure for two isolated application domains:

- Gateway: a public proxy running on EKS.
- Backend: a private service running on a separate EKS cluster.
- Private communication between the VPCs.
- Reusable Terraform modules.
- Infrastructure and application deployment through GitHub Actions.

## Project status

Initial setup. No AWS resources have been provisioned.

## Deployment rules

- Terraform apply runs only through GitHub Actions.
- EKS cluster and node IAM role names must start with eks-.
- Sentinel IAM role names must start with sentinel-.
- Permission restrictions must be respected and documented.
- Changes are developed in branches and reviewed through pull requests.
