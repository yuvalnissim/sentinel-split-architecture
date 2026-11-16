# Recreate and validate Sentinel

This runbook recreates the lab after teardown. All Terraform plan/apply
operations run in GitHub Actions. Local commands below prepare GitHub or
inspect AWS; none performs a local Terraform apply.

The revised bootstrap and discovery code has not yet been tested by a new
AWS deployment. Historical evidence proves the original lab worked, not
that this revised runbook has already passed end to end.

## 1. Scope and prerequisites

Defaults target AWS account `485378272094`, region `eu-north-1`, AZs
`eu-north-1a/b`, clusters `eks-gateway/backend`, and CIDRs `10.30.0.0/16`
and `10.40.0.0/16`. Use the assigned account and approved IAM prefixes.
Never work around an SCP. Record permission denials and request clarification.

You need:

- Git, AWS CLI v2, GitHub CLI (`gh`) and a GitHub account with Actions and
  repository-administration access. Windows PowerShell is supported locally.
- An unexpired AWS lab session, including its session token, available as
  profile `aws-lab`. Its lifetime must cover provisioning and teardown.
- Permission to create the documented resources and scoped role policies.
- Access to Systems Manager Session Manager for the private runner.
- Available EKS/EC2/NAT/Elastic IP quotas and non-overlapping VPC CIDRs.

Runner registration needs a repository administrator. A manual registration
step is intentional; no GitHub registration token is stored in Terraform.

For a different account, update `variables.tf`, `backend.tf`, workflow
account/registry/bucket defaults and the account guard in the cleanup script
before provisioning. For different CIDRs, also update the gateway DNS resolver
(`10.30.0.2` is the resolver for the configured gateway VPC). Cross-account
and cross-region portability are not implemented by this revision.

## 2. Clone and prepare GitHub (local PowerShell)

```powershell
git clone https://github.com/yuvalnissim/sentinel-split-architecture.git
Set-Location sentinel-split-architecture
git switch main
git pull --ff-only
gh auth login
gh auth status
aws sts get-caller-identity --profile aws-lab --region eu-north-1
```

If you already have the checkout, start with `git status`; preserve local
changes before updating. If using a fork, set its remote and use `gh repo
set-default OWNER/REPOSITORY` so subsequent commands target that fork.
Confirm the AWS identity belongs to the assigned account before continuing.

In GitHub **Settings → Environments**, create `bootstrap`. Store these three
environment secrets from the same current AWS session:

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | Session access key |
| `AWS_SECRET_ACCESS_KEY` | Session secret key |
| `AWS_SESSION_TOKEN` | Session token |

Paste secrets through the GitHub UI, never into source files, issues or logs.
Configure any required environment approvals. Enable Actions if GitHub has
disabled them. Keep application/tool/controller workflows disabled until
their prerequisites below exist. Do not push infrastructure edits in the
middle of bootstrap: push-triggered Terraform runs use both bootstrap flags
false and remove temporary access.

Prepare and merge the code before beginning live creation. Application jobs
require `main` and the self-hosted runner, and will otherwise queue or fail.

## 3. Check credentials and create remote state

```powershell
gh workflow enable bootstrap-check.yml
gh workflow run bootstrap-check.yml --ref main
gh run list --workflow bootstrap-check.yml --limit 1
```

Open the run and wait for success. An `ExpiredToken` requires refreshing all
three environment secrets, then rerunning. Enabling a workflow does not run it.

```powershell
gh workflow enable bootstrap-state.yml
gh workflow run bootstrap-state.yml --ref main
```

Wait for success before provisioning. Expected: bucket
`sentinel-tfstate-485378272094-eu-north-1`, encryption, versioning, blocked
public access and a policy requiring TLS. The main Terraform stack does not
create this bucket; `backend.tf` must match it. Never replace/delete an existing
state bucket containing a live environment's state.

## 4. Create infrastructure with temporary bootstrap permissions

```powershell
gh workflow enable validate.yml
gh workflow enable terraform-plan.yml
gh workflow run terraform-plan.yml --ref main `
  -f enable_cni_bootstrap=true `
  -f enable_controller_bootstrap=true
```

Wait for the complete run, including saved-plan apply. Expected outputs include
two clusters, two networks, private runner details, ECR repositories, a backend
ALB security group and VPC peering. Record the new runner instance ID from
the output; never use the ID from historical screenshots.

The CNI flag temporarily attaches `AmazonEKS_CNI_Policy` to node roles so
initial networking works before Pod Identity is installed. The controller
flag creates `sentinel-controller-installer`, its EKS access and the runner's
permission to assume it. Both are removed in later steps. Read
[CNI bootstrap](cni-bootstrap.md) before proceeding.

If apply fails, inspect the failed step and current state, fix the stated
cause and rerun with the same bootstrap settings. Do not manually recreate
Terraform-managed resources or remove state entries to hide a failure.

## 5. Register the private runner (Session Manager)

In AWS EC2, select the **new** `sentinel-private-runner` instance, choose
**Connect → Session Manager**, then connect. It has no public IP or SSH ingress.
Wait for SSM registration; use the EC2/SSM consoles if it is not yet online.

In its Bash session:

```bash
sudo dnf install -y git curl tar gzip unzip libicu
aws --version
sudo -iu ssm-user
mkdir -p ~/actions-runner
cd ~/actions-runner
sudo -n true
```

If the required OS dependency or sudo access is unavailable, resolve runner
preparation before registering; the installation workflows need passwordless
sudo. Do not configure copied bootstrap AWS credentials on this machine.

In GitHub **Settings → Actions → Runners → New self-hosted runner**, choose
**Linux / x64**. Execute GitHub's displayed download, checksum and extraction
commands in `~/actions-runner`. These commands provide the current supported
runner and a short-lived registration token; do not copy an old token from
documentation. Run its configuration command as `ssm-user` with:

- Runner name: `sentinel-private-runner`.
- Labels: retain the default `self-hosted`, `Linux`, `X64`; add `sentinel`.
- Working directory: `_work`.
- Runner group: the repository's permitted group (original lab: `Default`).

After configuration:

```bash
sudo ./svc.sh install ssm-user
sudo ./svc.sh start
sudo ./svc.sh status
```

Expected: the runner appears **Idle/Online** in GitHub. If an old destroyed
runner remains registered, remove that offline registration and register the
new machine; Terraform does not manage GitHub runner registrations.

## 6. Install tooling and verify identity

From local PowerShell, run each workflow only after the previous one succeeds:

```powershell
gh workflow enable runner-check.yml
gh workflow run runner-check.yml --ref main
gh workflow enable runner-tools.yml
gh workflow run runner-tools.yml --ref main
gh workflow enable install-runner-docker.yml
gh workflow run install-runner-docker.yml --ref main
```

Expected: runner-check reports the `sentinel-private-runner` EC2 role;
tool installation verifies Terraform, kubectl and Helm; Docker is active
and responds to `docker info`. A queued run usually means labels, runner
group access or the system service need attention.

## 7. Install controllers and verify CNI identity

```powershell
gh workflow enable install-lb-controllers.yml
gh workflow run install-lb-controllers.yml --ref main
```

Expected: controllers roll out successfully in both clusters. Their VPC IDs
are discovered with `eks:DescribeCluster`; no historical IDs need editing.
The installer role must still exist. A forbidden cluster-role operation
indicates missing temporary installer access; changing the runner's normal
application permissions to cluster-admin is not the solution.

Follow the complete [CNI bootstrap verification](cni-bootstrap.md) for both
clusters from the private runner. Confirm the dedicated CNI identity,
aws-node rollout and ready nodes before removing its temporary fallback.

## 8. Remove temporary access in two steps

First remove node-role CNI permissions while keeping installation/diagnostic
access for the post-removal checks:

```powershell
gh workflow run terraform-plan.yml --ref main `
  -f enable_cni_bootstrap=false `
  -f enable_controller_bootstrap=true
```

Wait for success; repeat the CNI rollout/readiness checks in the CNI guide.
Then remove installer access:

```powershell
gh workflow run terraform-plan.yml --ref main `
  -f enable_cni_bootstrap=false `
  -f enable_controller_bootstrap=false
```

Expected: temporary CNI attachments and installer resources are gone;
dedicated workload identities and ordinary application access remain.
Future controller upgrades must temporarily enable only the installer flag.
New/replacement node groups require explicit CNI bootstrap again.

## 9. Build and deploy backend, then gateway

```powershell
gh workflow enable build-backend.yml
gh workflow run build-backend.yml --ref main
```

Wait for success. It tests the backend container, publishes an immutable ECR
image, discovers `sentinel-backend-alb` in the backend cluster's current VPC,
renders that SG and image digest, performs server-side dry-run and deploys.
The runner's additional `DescribeSecurityGroups` read is restricted to the
configured region; AWS does not support individual-group resource scoping
for that API. Discovery fails if it cannot find exactly one valid group.

Ingress subnet IDs are omitted deliberately: the controller uses the
public/internal subnet role tags provisioned by Terraform. Checked-in
manifests contain environment placeholders; deploy them through the rendering
workflow, not directly with `kubectl apply -f k8s/...`.

After the backend succeeds:

```powershell
gh workflow enable build-gateway.yml
gh workflow run build-gateway.yml --ref main
```

The gateway workflow selects the backend's deployed digest for container
integration tests, waits for its current Ingress hostname, and renders that
hostname and the new gateway digest. An empty/unexpected hostname stops the
deployment rather than using the destroyed environment's address.

Subsequent relevant pushes to `main` trigger application build/deploy normally.
Container tests and Deployment rollout still do not replace live validation.

## 10. Validate the new live environment

On the runner (ordinary EC2 role, not the installer), configure fresh contexts:

```bash
aws eks update-kubeconfig --name eks-gateway --region eu-north-1 --alias sentinel-gateway
aws eks update-kubeconfig --name eks-backend --region eu-north-1 --alias sentinel-backend

for domain in gateway backend; do
  kubectl --context "sentinel-$domain" -n default get pods -l "app=sentinel-$domain" -o wide
  kubectl --context "sentinel-$domain" -n default get ingress "sentinel-$domain"
done
```

Expected: two ready application replicas per cluster and populated ALB
hostnames. Record the **new** public gateway and internal backend hostnames.
On your local Windows machine, set them from that output:

```powershell
$gatewayHost = "PASTE_NEW_PUBLIC_GATEWAY_HOSTNAME"
$backendHost = "PASTE_NEW_INTERNAL_BACKEND_HOSTNAME"
curl.exe --fail-with-body --connect-timeout 5 --max-time 20 "http://$gatewayHost/"
curl.exe --connect-timeout 5 --max-time 10 "http://$backendHost/"
```

Expected: the gateway returns `Hello from backend`; direct access to the
internal backend fails from an ordinary external connection without private
access. A timeout alone does not prove which security control blocked it.

Test the allowed internal source from a temporary Pod in the gateway cluster
(Bash on the runner):

```bash
set -euo pipefail
backend_host="$(kubectl --context sentinel-backend -n default get ingress sentinel-backend -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
backend_image="$(kubectl --context sentinel-backend -n default get deployment sentinel-backend -o jsonpath='{.spec.template.spec.containers[0].image}')"
kubectl --context sentinel-gateway -n default run backend-connectivity-check \
  --image="$backend_image" --restart=Never --command -- python -c \
  'import sys,urllib.request; print(urllib.request.urlopen(sys.argv[1],timeout=15).read().decode())' \
  "http://$backend_host/"
kubectl --context sentinel-gateway -n default wait --for=jsonpath='{.status.phase}'=Succeeded pod/backend-connectivity-check --timeout=120s
kubectl --context sentinel-gateway -n default logs backend-connectivity-check
kubectl --context sentinel-gateway -n default delete pod backend-connectivity-check
curl --connect-timeout 5 --max-time 10 "http://$backend_host/"
```

Expected: the Pod logs contain `Hello from backend`; the direct runner request
fails because its SG is not an allowed backend ALB source. Inspect SG rules
alongside this negative test. If the Pod fails, retain its describe/log output
for investigation and delete it afterwards. Public ALB readiness can lag
Deployment readiness; inspect Ingress events and target health before retrying.

Save fresh screenshots/run links with the commit SHA, date and expected vs
observed results in `docs/evidence/`. Explicitly distinguish this recreation
from the original November 2026 evidence.

## 11. Ordered teardown

After collecting evidence, prevent concurrent deployments and confirm no
application or infrastructure run remains active. Disable build-backend,
build-gateway, controller installation and terraform-plan workflows through
Actions or `gh workflow disable FILE`. Refresh bootstrap secrets if needed.
Keep the private runner, controllers and cleanup workflow available.

```powershell
gh workflow enable cleanup.yml
gh workflow run cleanup.yml --ref main -f confirmation=DESTROY-SENTINEL
```

Wait for all three jobs. The workflow deletes Ingresses while controllers
still run, deletes workloads, checks controller resources in the current
cluster VPCs, then plans/applies infrastructure destruction on a hosted runner.
The cleanup script aborts if either cluster cannot be discovered; investigate
partial teardown rather than supplying guessed VPC IDs or removing finalizers.

Verify the empty Terraform state and absence of the project EKS clusters,
VPCs, ALBs, active EC2 instances, NAT Gateways and ECR repositories in AWS.
The state bucket remains separate. Retain it if needed for audit/recovery;
delete it only after confirming no live resources need its state. A versioned
bucket needs all object versions and delete markers removed, not only the
current objects. Do not commit or publish Terraform state as evidence.

Remove the destroyed runner's GitHub registration and all three bootstrap
secrets. Record teardown evidence. Do not claim zero account-wide charges
from an empty project state: unrelated resources and retained storage require
their own checks.
