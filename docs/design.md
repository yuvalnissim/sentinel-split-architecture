# Sentinel architecture design

## Goal

Expose a public gateway that forwards requests to a private backend
in a separate VPC. A successful request returns "Hello from backend".

## Networks

| Domain | VPC CIDR | Private subnet A | Private subnet B |
|---|---|---|---|
| Gateway | 10.30.0.0/16 | 10.30.11.0/24 | 10.30.12.0/24 |
| Backend | 10.40.0.0/16 | 10.40.11.0/24 | 10.40.12.0/24 |

Both VPCs use eu-north-1 and two Availability Zones.

Public subnets will host internet-facing load balancers and public NAT
Gateways where required. EC2 instances will use private subnets only.

VPC Peering will connect the networks. Routes and security groups will
permit only the communication required by the applications and management.

## Kubernetes

- eks-gateway runs the proxy.
- eks-backend runs the backend service.
- Both clusters use private Kubernetes API endpoints.
- Worker nodes have no public IP addresses.
- Each cluster has its own IAM roles and security groups.

## Application traffic

1. A client connects to the public gateway load balancer.
2. The gateway proxy forwards the request over VPC Peering.
3. An internal backend load balancer forwards it to backend pods.
4. The backend response returns through the proxy to the client.

Kubernetes ClusterIP addresses are not used for cross-cluster access.

Backend ingress will be restricted to the approved gateway sources.
The exact rules will be documented with the selected load balancer design.

## Terraform structure

Reusable modules:

- networking
- peering
- iam
- eks

The root configuration composes the modules for the two domains.

## CI/CD

- Pull requests run static validation.
- Pushes to main trigger the deployment pipeline.
- Terraform plan and apply run only through GitHub Actions.
- Terraform state is stored remotely with encryption and locking.
- Application images are built and published to a container registry.
- Deployment jobs require private connectivity to both Kubernetes APIs.
- A cleanup workflow removes workloads and infrastructure in order.

## IAM naming

- EKS cluster and node roles start with eks-.
- Sentinel automation and workload roles start with sentinel-.

## Observed account constraints

Listing IAM OIDC providers is explicitly denied by an organization SCP.
Creating an IAM OIDC provider was also denied in the previous lab.

GitHub OIDC federation is therefore not assumed to be available.
No attempt will be made to bypass the restriction.

## Bootstrap authentication

The proposed bootstrap uses short-lived AWS session credentials stored
as GitHub Actions secrets, not committed to Git.

A private self-hosted runner can subsequently use an EC2 IAM role.
The bootstrap permissions, credential lifetime, runner setup, and remote
state creation must be verified before provisioning.

No local Terraform apply is permitted.

## Cost controls

Prepare and validate code before provisioning EKS and NAT Gateways.
Use small worker instances and document availability trade-offs.
Destroy the environment after collecting validation evidence.

## Status

Design only. No AWS resources have been created for this project.