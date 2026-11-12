# Architecture decisions

## Goal

Provide a public HTTP entry point that forwards requests to a private backend in a separate VPC.

The implementation separates public entry, application execution and Kubernetes management access.

## Implemented topology

| Component | Gateway domain | Backend domain |
|---|---|---|
| VPC | 10.30.0.0/16 | 10.40.0.0/16 |
| EKS cluster | eks-gateway | eks-backend |
| Application | NGINX reverse proxy | Python HTTP backend |
| Application entry point | Internet-facing ALB | Internal ALB |
| Kubernetes API | Private | Private |
| Worker placement | Two private subnets | Two private subnets |

Both domains use eu-north-1a and eu-north-1b.

A private self-hosted GitHub Actions runner resides in the gateway VPC.

## Why separate VPCs and clusters?

The assignment requires separate application domains.

Separate VPCs provide distinct address spaces, routing and security controls. Separate EKS clusters provide independent Kubernetes management boundaries.

The trade-off is higher infrastructure cost and more components to operate than a single cluster with namespaces.

## Why VPC Peering?

There are two VPCs in the same account and region. Peering provides a direct private path without requiring a transit hub.

Private route tables contain routes to the other VPC.

A route establishes reachability; security groups determine which traffic is permitted. Neither replaces the other.

Peering is non-transitive and would require reconsideration if the network expanded substantially.

## Why an internal backend ALB?

Kubernetes ClusterIP addresses are local to their cluster's service network and are not used as cross-cluster endpoints.

The internal ALB gives the gateway an entry point independent of individual backend Pod IPs.

The controller manages application targets as Pods change. The additional ALB introduces cost and another component in the request path.

## Backend access boundary

The backend ALB security group permits inbound HTTP from the gateway cluster security group.

Its application egress targets the backend cluster security group on port 8080. The controller manages the corresponding backend security rules.

The runner has a different security group. A direct request from the runner to the backend ALB timed out during validation.

This boundary trusts resources associated with the gateway cluster security group. It is not an application-specific or per-Pod authorization boundary.

No Kubernetes NetworkPolicy has been configured.

## Private management

Both EKS APIs accept private network access only.

The runner reaches the gateway API locally and the backend API through peering. API security rules permit HTTPS from the runner security group.

Network access and Kubernetes authorization are separate requirements. The runner must have both to deploy.

Systems Manager provides runner administration without opening SSH.

## Outbound access

Private resources use NAT Gateways for outbound access, including package and image downloads.

There is one NAT Gateway per VPC, placed in one Availability Zone. Private subnets in both AZs share it.

This reduces cost compared with a NAT Gateway per AZ, but introduces a shared AZ dependency and potential cross-AZ data charges.

Application traffic between the VPCs uses peering rather than NAT.

## IAM identities

Cluster and worker role names start with eks-. Other project roles start with sentinel-.

Distinct roles serve:

- EKS control planes.
- EKS worker nodes.
- The private runner.
- VPC CNI workloads.
- AWS Load Balancer Controller workloads.

EKS Pod Identity supplies credentials to the CNI and load balancer controllers.

Credential retrieval through the dedicated CNI roles was verified before removing the CNI policy from the node roles.

## Controller installation access

Installing the controller requires cluster-scoped Kubernetes resources.

A temporary installer role received cluster-admin access in both clusters. The runner could assume that role during installation.

After successful installation, the installer role, access entries, access policy associations and runner assume-role policy were removed.

Controller runtime permissions come from its separate Pod Identity role and do not depend on keeping the installer role.

Future installations and upgrades require temporarily restoring installation access.

## Account constraints

IAM OIDC provider operations were denied by an organization SCP.

The project did not bypass that restriction. Infrastructure bootstrap uses short-lived AWS session credentials stored in the GitHub bootstrap environment.

Application automation uses the runner's EC2 role and does not require those copied credentials.

## Infrastructure as code

Reusable Terraform modules manage networking, peering, EKS, the runner, runner IAM and ECR.

Root configuration composes modules and defines cross-component access policies.

Terraform state uses a separately bootstrapped S3 bucket with encryption, versioning, public-access protection and lock-file locking.

Terraform plan and apply run through GitHub Actions.

## Application delivery

Each application has one workflow that builds, tests, publishes and deploys.

The pipeline retrieves the published ECR digest and uses Kustomize to render a temporary manifest containing that exact image reference.

Server-side dry-run validation precedes apply. The workflow waits for rollout and checks the Deployment's image reference.

Gateway integration tests use the digest-pinned backend image selected from the backend Deployment.

The workflows do not automatically roll back failed deployments or commit promoted digests to Git. Backend changes do not automatically trigger the gateway workflow.

## Availability

Each cluster has two managed worker nodes and each application has two replicas.

Application topology spread constraints distribute replicas across hostnames. The observed deployments placed replicas on separate nodes in separate AZs.

Hostname spreading alone is not a guarantee of AZ-level placement for every future topology.

CoreDNS placement, NAT dependencies, replica capacity and failure recovery require further review before claiming production availability.

## Validation and its limits

Successful tests include:

- Gateway-cluster Pod to internal backend ALB.
- Local client through public gateway ALB to backend.
- Browser through public gateway ALB to backend.
- Application container health, response and unknown-route behavior.
- Deployment rollout and image-reference verification.

Negative tests include direct backend requests from the local computer and the runner.

Timeouts demonstrate failed access attempts from those sources. They do not independently prove which control blocked the requests or establish comprehensive isolation.

No load tests or controlled AZ-failure tests have been performed.

## Remaining operational work

- Implement and verify an ordered teardown workflow.
- Improve PR checks for application code, manifests and workflow YAML.
- Reduce hardcoded environment references for recreation.
- Define release promotion, rollback and stale-rerun handling.
- Revalidate the complete request path after changes.

## Production improvements

TLS, application authentication, NetworkPolicy enforcement, observability, supply-chain checks and broader resilience testing are outside the completed functional demonstration.