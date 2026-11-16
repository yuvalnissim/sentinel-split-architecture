# CNI bootstrap and steady-state permissions

The original lab was provisioned with node-role CNI permissions and later
migrated to Pod Identity. Applying only the final permissions to an empty
account can prevent nodes from becoming ready: the Pod Identity Agent is
installed after the node group, and the CNI Pod Identity association after
the agent. This guide makes that initial permission transition explicit.

## First creation or node-group replacement

1. Restore the state bucket and valid short-lived `bootstrap` credentials.
2. Run **Terraform deploy** manually on `main`, selecting
   `enable_cni_bootstrap: true` and `enable_controller_bootstrap: true`. This attaches `AmazonEKS_CNI_Policy` to each
   node role before node-group creation. The dedicated CNI roles, agent and
   associations are then installed through the existing dependency order.
3. Register and prepare the private runner. Temporarily enable the
   controller installer role and its cluster-admin access using the workflow
   input (already enabled in step 2), as required for controller installation. Use that role for the private API checks below.
4. Verify CNI Pod Identity in both clusters before running another normal
   infrastructure deployment. Push-triggered deployments use bootstrap=false
   and will remove the temporary policies.

The bootstrap flag defaults to false. A plan guard blocks creation or
replacement of node groups when their temporary policy is absent. It does
not grant AWS permissions or execute an apply itself.

## Verify before removing the temporary policy

Run from the private runner with the AWS CLI and kubectl installed.
The installer role is needed for diagnostic resources in `kube-system`;
the runner's usual namespace-scoped edit access is insufficient.

For each domain (`gateway`, then `backend`):

```bash
set -euo pipefail
umask 077
domain=gateway
account="$(aws sts get-caller-identity --query Account --output text)"
kubeconfig="$(mktemp)"
trap 'rm -f -- "$kubeconfig"' EXIT

aws eks update-kubeconfig \
  --name "eks-$domain" --region eu-north-1 \
  --role-arn "arn:aws:iam::$account:role/sentinel-controller-installer" \
  --kubeconfig "$kubeconfig"
export KUBECONFIG="$kubeconfig"

kubectl -n kube-system rollout status daemonset/eks-pod-identity-agent --timeout=300s
kubectl -n kube-system rollout restart daemonset/aws-node
kubectl -n kube-system rollout status daemonset/aws-node --timeout=300s
kubectl wait --for=condition=Ready nodes --all --timeout=300s
```

Check the association through the AWS EKS console using the bootstrap
identity (the runner intentionally lacks permission to list associations).
For `aws-node` in `kube-system`, confirm the role is
`sentinel-eks-<domain>-cni`, and confirm both add-ons report `ACTIVE`.

To test the service account's credentials without falling back to the
node's instance role, run this temporary diagnostic Pod:

```bash
kubectl -n kube-system run cni-identity-check \
  --image=public.ecr.aws/aws-cli/aws-cli:latest \
  --restart=Never \
  --env=AWS_EC2_METADATA_DISABLED=true \
  --overrides='{"spec":{"serviceAccountName":"aws-node","hostNetwork":true,"dnsPolicy":"ClusterFirstWithHostNet"}}' \
  -- sts get-caller-identity --query Arn --output text

kubectl -n kube-system wait --for=jsonpath='{.status.phase}'=Succeeded \
  pod/cni-identity-check --timeout=180s
identity="$(kubectl -n kube-system logs cni-identity-check)"
case "$identity" in
  "arn:aws:sts::$account:assumed-role/sentinel-eks-$domain-cni/"*)
    echo "Dedicated CNI role verified." ;;
  *) echo "Unexpected CNI identity; keep bootstrap permissions."; exit 1 ;;
esac
kubectl -n kube-system delete pod cni-identity-check --wait=true
```

The diagnostic image tag is used only for this manual check, not deployed
as an application release. Use an approved digest if image pinning is
required. If the check fails, inspect its logs and delete the diagnostic Pod
after investigation. Keep bootstrap permissions enabled until resolved.
The diagnostic confirms service-account credential delivery; node readiness
and the aws-node rollout are separate checks of the running CNI.

## Remove bootstrap permissions

After verification in both clusters:

1. Run **Terraform deploy** manually with `enable_cni_bootstrap: false` and
   `enable_controller_bootstrap: true` to retain diagnostic access temporarily.
   Inspect the plan: the temporary node-role CNI policy attachments should
   be removed, while the dedicated CNI role attachments remain.
2. Repeat the aws-node restart, rollout and node-readiness checks. After
   application deployment, run the new-Pod and cross-cluster checks in
   reproduction runbook step 10. Removing the fallback policy must not break
   new Pod networking.
3. Run **Terraform deploy** with both bootstrap inputs false after controller
   setup and these verification steps are complete. This removes temporary
   controller installation access.

If post-removal checks fail, rerun the infrastructure workflow with
bootstrap=true, investigate the Pod Identity path, then repeat verification.
Do not perform local Terraform apply, bypass the SCP, or add permanent CNI
permissions to the node roles.

This code path has local plan-guard tests. A clean AWS creation and the
post-removal network checks have not yet been rerun for this revision.
