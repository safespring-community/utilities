# Certificate management

- [Certificate management](#certificate-management)
  - [Prerequisites](#prerequisites)
  - [Installation steps](#installation-steps)
    - [Step 1: Install cert-manager](#step-1-install-cert-manager)
    - [Step 2: Create ACME accounts](#step-2-create-acme-accounts)
    - [Step 3: Requesting certificates](#step-3-requesting-certificates)
    - [Step 4: Patching controllers](#step-4-patching-controllers)
    - [Step 5: Modify kubeconfig](#step-5-modify-kubeconfig)
    - [Step 6: Cleanup](#step-6-cleanup)
  - [Why is not the cert-manager operator from OperatorHub used?](#why-is-not-the-cert-manager-operator-from-operatorhub-used)
  - [Final Remarks](#final-remarks)
    - [Next Steps](#next-steps)

This guide provides instructions for installing cert-manager with a webhook for Gandi DNS in your environment. Cert-manager is a Kubernetes add-on to automate the management, issuance, and renewal of certificates from various issuing sources. It will ensure your services are securely served over HTTPS within your cluster.

## Prerequisites

Before proceeding with the installation, ensure you have the following:
- Access to a Kubernetes cluster with administrative privileges.
- The `helm` and `oc` (OpenShift CLI)  installed on your local machine. You can also replace all oc command with kubectl.
- A Gandi account and an API key for domain validation.

## Installation steps

### Step 1: Install cert-manager

1. **Create a Namespace**: Start by creating a namespace for cert-manager to organize its resources without cluttering other parts of your cluster.

   ```bash
   namespace="cert-manager"
   oc create namespace ${namespace} || true
   ```

2. **Add Helm Repositories**: Add the Jetstack and Sintef-Gandi helm repositories. These contain the charts needed to install cert-manager and the Gandi DNS webhook.

   ```bash
   helm repo -n ${namespace} add jetstack https://charts.jetstack.io
   helm repo -n ${namespace} add sintef-gandi https://sintef.github.io/cert-manager-webhook-gandi
   helm dependency build .
   ```
3. **Install cert-manager**: Use Helm to install cert-manager within the created namespace. This step also includes creating a secret for the Gandi API token which is required for DNS challenges.

   ```bash
   helm install -n ${namespace} cert-manager .

   # Replace '..........' with your actual Gandi API Key.
   #GANDI_KEY=..........
   oc create --namespace ${namespace} secret generic gandi-credentials  --from-literal=api-token="$(echo ${GANDI_KEY})"
   ```

### Step 2: Create ACME accounts

Cert-manager uses ACME protocol to automatically issue and renew certificates. You'll need to create accounts for both LetsEncrypt staging and production environments.

- **Staging Environment**: Useful for testing. Certificates issued from this environment are not trusted by browsers.
  ```yaml
  oc apply -f - <<EOF
  apiVersion: cert-manager.io/v1
  kind: ClusterIssuer
  metadata:
    name: letsencrypt-staging
  spec:
    acme:
      server: https://acme-staging-v02.api.letsencrypt.org/directory
      email: not-valid@safespring.com
      privateKeySecretRef:
        name: letsencrypt-staging
      solvers:
      - dns01:
          webhook:
            groupName: acme.bwolf.me
            solverName: gandi
            config:
              apiKeySecretRef:
                key: api-token
                name: gandi-credentials
  EOF
  ```

- **Production Environment**: Use this for obtaining trusted certificates after testing.
  ```yaml
  oc apply -f - <<EOF
  apiVersion: cert-manager.io/v1
  kind: ClusterIssuer
  metadata:
    name: letsencrypt
  spec:
    acme:
      server: https://acme-v02.api.letsencrypt.org/directory
      email: not-valid@safespring.com
      privateKeySecretRef:
        name: letsencrypt
      solvers:
      - dns01:
          webhook:
            groupName: acme.bwolf.me
            solverName: gandi
            config:
              apiKeySecretRef:
                key: api-token
                name: gandi-credentials
  EOF
  ```

### Step 3: Requesting certificates

Request certificates for both your applications' ingress controller and the cluster API. Ensure to customize the `dnsNames` field with your cluster's domain details.

- **Applications Ingress Controller**: This certificate will secure your applications accessible via the ingress.

  ```yaml
  oc apply -f - <<EOF
  apiVersion: cert-manager.io/v1
  kind: Certificate
  metadata:
    name: apps-wildcard-staging
    namespace: openshift-ingress
  spec:
    dnsNames:
    - '*.apps.<cluster_name>.<domain>'
    issuerRef:
      kind: ClusterIssuer
      name: letsencrypt-staging
    secretName: apps-wildcard-tls-staging
  EOF
  ```

- **Cluster API**: This certificate is for securing the Kubernetes API server.
  ```yaml
  oc apply -f - <<EOF
  apiVersion: cert-manager.io/v1
  kind: Certificate
  metadata:
    name: api-staging
    namespace: openshift-config
  spec:
    dnsNames:
    - 'api.<cluster_name>.<domain>'
    issuerRef:
      kind: ClusterIssuer
      name: letsencrypt-staging
    secretName: api-tls-staging
  EOF
  ```

### Step 4: Patching controllers

To use the requested certificates, patch the default ingress controller and the API server with the names of the secrets where the certificates are stored.

- **Default Ingress Controller**:

  To see if certificate is ready to be used:
  ```bash
  oc wait --timeout=200s -n openshift-ingress --for=condition=Ready certificate/apps-wildcard-staging
  ```

  Patch ingress controller when certificate is ready inside the secret:
  ```bash
  oc patch ingresscontroller.operator default --type=merge -p '{"spec":{"defaultCertificate": {"name": "apps-wildcard-tls-staging"}}}' -n openshift-ingress-operator
  ```

- **API Server**:

  Verify that the certificate has been successfully retrieved:
  ```bash
  oc wait --timeout=200s -n openshift-config --for=condition=Ready certificate/api-staging
  ```

  Patch apiserver to use this new certificate:
  ```bash
  oc patch apiserver cluster --type=merge -p '{"spec":{"servingCerts": {"namedCertificates": [{"names": ["api.<cluster_name>.<domain>"], "servingCertificate": {"name": "api-tls-staging"}}]}}}'
  ```

### Step 5: Modify kubeconfig

To ensure your Kubernetes client (kubectl) trusts the new certificates, you may need to modify your kubeconfig file. Remove the certificate-authority-data part from your kubeconfig.

```bash
sed -i '/certificate-authority-data/d' kubeconfig
```

### Step 6: Cleanup
If you need to uninstall cert-manager and clean up its resources, use the following commands:

```bash
namespace="cert-manager"
helm uninstall -n ${namespace} cert-manager
oc delete secret -n ${namespace} gandi-credentials

oc delete --ignore-not-found=true -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

oc delete namespace cert-manager
```

## Why is not the cert-manager operator from OperatorHub used?

The decision to not utilize the cert-manager operator available on OperatorHub stems from a specific limitation regarding the ACME DNS-01 challenge verification process. The core issue is that the cert-manager operator lacks the functionality to specify an alternative DNS service for verifying ACME DNS-01 challenges. By default, cert-manager would resort to using the internal DNS provided by OKD, which is incapable of resolving DNS-01 challenges. This limitation is recognized and tracked in the cert-manager's issue tracker under the ticket titled ["Support configuration via operator subscription"](https://github.com/cert-manager/cert-manager/issues/4410).

Furthermore, while Red Hat offers a tailored cert-manager package within OpenShift that includes support for specifying `dns01RecursiveNameservers`, this particular operator version is not available for OKD environments. This discrepancy necessitates our approach of manually installing cert-manager using Helm charts, ensuring we can accurately configure DNS settings to meet our verification needs for ACME DNS-01 challenges.


## Final Remarks

Congratulations on successfully setting up cert-manager with Gandi DNS for your Kubernetes environment. This setup ensures your services are not only securely served over HTTPS but also streamlines the management, issuance, and renewal of certificates—automating what was once a manual and error-prone process.

### Next Steps

With your certificate infrastructure in place, consider the following to further secure and optimize your environment:
- **Monitor Your Certificates**: Implement monitoring and alerting for certificate expirations and renewals to ensure continuous uptime for your services. Maybe [cert-utils-operator](https://github.com/redhat-cop/cert-utils-operator) can help you here.
