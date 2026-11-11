data "aws_iam_policy_document" "lb_controller_trust" {
  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRole",
      "sts:TagSession",
    ]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes-namespace"
      values   = ["kube-system"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes-service-account"
      values   = ["aws-load-balancer-controller"]
    }
  }
}

resource "aws_iam_role" "lb_controller" {
  name               = "sentinel-${var.cluster_name}-lb-controller"
  assume_role_policy = data.aws_iam_policy_document.lb_controller_trust.json
}

resource "aws_iam_policy" "lb_controller" {
  name = "sentinel-${var.cluster_name}-lb-controller"

  description = "AWS Load Balancer Controller permissions for ${var.cluster_name}"

  policy = file("${path.module}/policies/lb-controller-v3.6.2.json")
}

resource "aws_iam_role_policy_attachment" "lb_controller" {
  role       = aws_iam_role.lb_controller.name
  policy_arn = aws_iam_policy.lb_controller.arn
}

resource "aws_eks_pod_identity_association" "lb_controller" {
  cluster_name    = aws_eks_cluster.this.name
  namespace       = "kube-system"
  service_account = "aws-load-balancer-controller"
  role_arn        = aws_iam_role.lb_controller.arn

  depends_on = [
    aws_iam_role_policy_attachment.lb_controller,
    aws_eks_addon.pod_identity_agent,
  ]
}