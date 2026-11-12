# Architecture decisions

## Project lifecycle

The lab was deployed and validated successfully, then destroyed on
12 November 2026.

The architecture below describes the validated environment. Its application
endpoints are no longer active.

The ordered teardown workflow completed successfully and verified an empty
Terraform state. Follow-up AWS checks returned no EKS clusters, neither
project VPC, and no active project-tagged EC2 instances.

The separately bootstrapped S3 state bucket was subsequently emptied and
deleted, including its object versions and delete markers.

## Goal

Provide a public HTTP entry point that forwards requests to a private backend
in a separate VPC.

The implementation separates public entry, application execution and
Kubernetes management access.

## Implemented topology

| Component | Gateway domain | Backend domain |
|---|---|---|
| VPC | 10.30.0.0/16 | 10.40.0.0/16 |
| EKS cluster | eks-gateway | eks-backend |
| Application | NGINX reverse proxy | Python HTTP backend |
| Application entry point | Internet-facing ALB | Internal ALB |
| Kubernetes API | Private | Private |
| Worker placement | Two private subnets | Two private subnets |

Both domains used eu-north-1a and eu-north-1b.

A private self-hosted GitHub Actions runner resided in the gateway VPC.

## Why separate VPCs and clusters?

The assignment requires separate application domains.

Separate VPCs provide distinct address spaces, routing and security controls.
Separate EKS clusters provide independent Kubernetes management boundaries.

The trade-off is higher infrastructure cost and more components to operate
than a single cluster with namespaces.

## Why VPC Peering?

The two VPCs were in the same account and region. Peering provided a direct
private path without requiring a transit hub.

Private route tables contained routes to the other VPC.

A route establishes reachability; security groups determine which traffic
is permitted. Neither replaces the other.

Peering is non-transitive and would require reconsideration if the network
expanded substantially.

## Why an internal backend ALB?

Kubernetes ClusterIP addresses were not used as cross-cluster endpoints.

The internal ALB gave the gateway an entry point independent of individual
backend Pod IPs.

The controller managed application targets as Pods changed. The additional
ALB introduced cost and another component in the request path.

## Backend access boundary

The backend ALB security group permitted inbound HTTP from the gateway
cluster security group.

Its application egress targeted the backend cluster security group on port
8080. The controller managed the corresponding backend security rules.

The runner had a different security group. A direct request from the runner
to the backend ALB timed out during validation.

This boundary trusted resources associated with the gateway cluster
security group. It was not an application-specific or per-Pod authorization
boundary.

Kubernetes NetworkPolicy was not configured or validated.

## Private management

Both EKS APIs accepted private network access only.

The runner reached the gateway API within its VPC and the backend API
through peering. API security rules permitted HTTPS from the runner
security group.

Network access and Kubernetes authorization are separate requirements.
The runner needed both to deploy.

Systems Manager provided runner administration without opening SSH.

## Outbound access

Private resources used NAT Gateways for outbound access, including package
and image downloads.

There was one NAT Gateway per VPC, placed in one Availability Zone. Private
subnets in both AZs shared it.

This reduced cost compared with a NAT Gateway per AZ, but introduced a
shared AZ dependency and potential cross-AZ data charges.

Application traffic between the VPCs used peering rather than NAT.

## IAM identities

Cluster and worker role names started with eks-. Other project role names
started with sentinel-.

Distinct roles served:

- EKS control planes.
- EKS worker nodes.
- The private runner.
- VPC CNI workloads.
- AWS Load Balancer Controller workloads.

EKS Pod Identity supplied credentials to the CNI and load balancer
controllers.

Credential retrieval through the dedicated CNI roles was verified before
removing the CNI policy from the node roles.

## Controller installation access

Installing the controller required cluster-scoped Kubernetes resources.

A temporary installer role received cluster-admin access in both clusters.
The runner could assume that role during installation.

After successful installation, the installer role, access entries, access
policy associations and runner assume-role policy were removed.

Controller runtime permissions came from separate Pod Identity roles and
did not depend on keeping the installer role.

Reinstalling or upgrading controllers in a recreated environment requires
temporarily restoring installation access.

## Account constraints

IAM OIDC provider operations were denied by an organization SCP.

The project did not bypass that restriction. Infrastructure bootstrap used
short-lived AWS session credentials stored in the GitHub bootstrap
environment.

Application automation used the runner's EC2 role and did not require
those copied credentials.

Expired bootstrap sessions caused workflow failures. Credentials were
refreshed and the failed jobs were rerun.

## Infrastructure as code

Reusable Terraform modules manage networking, peering, EKS, the runner,
runner IAM and ECR.

Root configuration composes modules and defines cross-component access
policies.

Terraform state was stored in a separately bootstrapped S3 bucket with
encryption, versioning, public-access protection and lock-file locking.

Terraform plan, apply and infrastructure destruction ran through GitHub
Actions.

Validation includes formatting, terraform validate and recursive TFLint
checks using the built-in Terraform rules.

## Application delivery

Each application has one workflow that builds, tests, publishes and deploys.

The pipeline retrieves the published ECR digest and uses Kustomize to render
a temporary manifest containing that exact image reference.

Server-side dry-run validation precedes apply. The workflow waits for
rollout and checks the Deployment's image reference.

Gateway integration tests use the digest-pinned backend image selected
from the backend Deployment.

The workflows do not automatically roll back failed deployments or commit
promoted digests to Git. Backend changes do not automatically trigger the
gateway workflow.

Application build and integration tests run after merge to main. Current
PR checks cover Terraform, not all application code, manifests or workflow
YAML.

## Availability

Each cluster had two managed worker nodes and each application had two
replicas.

Application topology spread constraints distributed replicas across
hostnames. The observed deployments placed replicas on separate nodes in
separate AZs.

Hostname spreading alone does not guarantee AZ-level placement for every
future topology.

CoreDNS placement, NAT dependencies, replica capacity and failure recovery
require further review before claiming production availability.

## Validation and its limits

Successful tests included:

- Gateway-cluster Pod to internal backend ALB.
- Local client through public gateway ALB to backend.
- Browser through public gateway ALB to backend.
- Application container health, response and unknown-route behavior.
- Deployment rollout and image-reference verification.
- A repeated public end-to-end request after the unified delivery pipelines
  were introduced.

Negative tests included direct backend requests from the local computer
and the runner.

Timeouts demonstrated failed access attempts from those sources. They did
not independently prove which control blocked the requests or establish
comprehensive isolation.

No load tests or controlled AZ-failure tests were performed.

Evidence is documented in [evidence/README.md](evidence/README.md).

## Ordered teardown

The manually triggered workflow is defined in
.github/workflows/cleanup.yml.

It requires the main branch and the explicit confirmation string
DESTROY-SENTINEL.

Before execution, infrastructure and application deployment workflows were
disabled and bootstrap credentials were refreshed.

The cleanup sequence was:

1. Verify bootstrap credentials and the AWS account.
2. Use the private runner to delete application Ingress resources while
   controllers and worker nodes were still available.
3. Delete application Deployments and Services.
4. Continue on a GitHub-hosted runner.
5. Verify that no ALBs or target groups remained in the project VPCs.
6. Check controller-created shared security groups and their references.
7. Remove recognized controller rules and unused shared security groups
   when present.
8. Create and apply a saved Terraform destroy plan.
9. Verify that Terraform state contained no managed resources.

The cleanup script checks account, VPCs, controller tags, network-interface
attachments and rule descriptions. Unexpected dependencies stop cleanup
for review.

The GitHub-hosted runner performs infrastructure destruction because the
private runner itself is part of the infrastructure being deleted.

## Teardown observations

The first gateway Ingress deletion attempt timed out. Subsequent checks
confirmed that both the Ingress and its ALB had disappeared. The failed
jobs were rerun without removing finalizers manually.

A later attempt stopped because bootstrap credentials had expired.
Credentials were refreshed and the failed jobs were rerun.

The final workflow run succeeded.

Follow-up checks confirmed:

- No EKS clusters listed in eu-north-1.
- Neither project VPC remained.
- No active project-tagged EC2 instances remained.

The S3 state bucket was outside the main Terraform configuration. It was
emptied and deleted separately after infrastructure destruction.

GitHub runner registration and environment secrets are separate from AWS
infrastructure and require separate administrative cleanup.

## Recreation requirements

The removed environment is not restored by running an application workflow.

Recreation requires:

- Recreating the remote state bucket.
- Restoring valid bootstrap credentials.
- Reviewing account-specific and hardcoded resource references.
- Re-enabling the required deployment workflows.
- Deploying infrastructure through GitHub Actions.
- Registering and preparing the private runner.
- Installing controllers using temporary installation access.
- Building and deploying the applications.
- Updating the gateway backend URL if the internal ALB hostname changes.
- Repeating connectivity and access-restriction checks.

## Future operational improvements

- Add PR checks for application code, manifests and workflow YAML.
- Reduce hardcoded environment references for recreation.
- Define release promotion, rollback and stale-rerun handling.
- Add a non-destructive inspection mode for cleanup.
- Improve credential-lifetime checks before lengthy operations.
- Revalidate the complete request path after changes.

## Production improvements

TLS, application authentication, NetworkPolicy enforcement, observability,
supply-chain checks and broader resilience testing remain outside the
completed functional demonstration.