# Cert-manager on OKD

First export the KUBECONFIG environment variable to authenticate as
cluster-admin.

```
$ export KUBECONFIG=./installer/auth/kubeconfig
```

## Install cert manager operator

Create a new namespace/project:
```
$ oc create namespace cert-manager
```

Create a global operator group in project (apply this):
```
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: cert-manager
  namespace: cert-manager
```
More info: https://docs.openshift.com/container-platform/4.9/operators/understanding/olm/olm-understanding-operatorgroups.html

Finding cert-manager operator metadata
```
oc describe packagemanifest cert-manager
```

Install the operator to the project (apply this)
```
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: cert-manager
  namespace: cert-manager
spec:
  channel: stable
  name: cert-manager
  source: community-operators
  sourceNamespace: openshift-marketplace
```

## Create webhook for certmanager to verify dns01 challenges with Gandi DNS

There is no dns01 provider for Gandi DNS API built into cert-manager, but this
webhook implements the necessary glue to let cert-manager do
dns01-verifications with gandi.
```
git clone https://github.com/safespring-community/cert-manager-webhook-gandi.git
cd cert-manager-webhook-gandi
less README.md
```

When/if this PR (https://github.com/bwolf/cert-manager-webhook-gandi/pull/18)
is merged you can switch to use the upstream repository
https://github.com/bwolf/cert-manager-webhook-gandi

Install the webhook helm chart.
```
$ helm install cert-manager-webhook-gandi \
    --namespace cert-manager \
    --set features.apiPriorityAndFairness=true \
    --set image.repository=bwolf/cert-manager-webhook-gandi \
    --set image.tag=latest \
    --set logLevel=2 \
    ./cert-manager-webhook-gandi/deploy/cert-manager-webhook-gandi
```

Create secret with your gandi api key
```
$ oc create secret generic gandi-credentials \
    --namespace cert-manager --from-literal=api-token="$(echo ${GANDI_KEY})"
```

# Create a cluster issuer

This will create a cluster issuer with the LetsEncrypti staging environment. When this
is working, switch to the production ernvironment to get proper certificates
with full trust chain. The staging environment is good for testing to avoid consuming from
the rate-limited production API of LetsEncrypt

Remember to set a valid email address.

To create the LE-staging cluster issuer, apply this
```
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    # The ACME server URL
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    # Email address used for ACME registration
    email: invalid@example.com
    # Name of a secret used to store the ACME account private key
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
```

## Ingress wildcard cert for `*.apps.<cluster_name>.<domain>`


Apply this: (remember quotes around the dnsname)
```
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: okd-apps-wildcard
  namespace: openshift-ingress
spec:
  dnsNames:
  - '*.apps.<cluster_name>.<domain>'
  issuerRef:
    kind: ClusterIssuer
    name: letsencrypt-staging
  secretName: okd-apps-wildcard-tls
```
If all goes well a new secret named `okd-apps-wildcard-tls` should appear in
the `openshift-ingress` namespace/project after a while

Then patch the ingress controller to use the new cert.
```
$ oc patch ingresscontroller.operator default --type=merge -p '{"spec":{"defaultCertificate": {"name": "okd-apps-wildcard-tls"}}}' -n openshift-ingress-operator
```

Ref: https://docs.okd.io/latest/security/certificates/replacing-default-ingress-certificate.html

# API server certificate


Apply this: (remember quotes around the dnsname)
```
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: okd-api
  namespace: openshift-config
spec:
  dnsNames:
  - 'api.<cluster_name>.<domain>'
  issuerRef:
    kind: ClusterIssuer
    name: letsencrypt-staging
  secretName: okd-api-tls
```

Then patch openshift config to use the new cert for API
```
$ oc patch apiserver cluster --type=merge -p '{"spec":{"servingCerts": {"namedCertificates": [{"names": ["<FQDN>"], "servingCertificate": {"name": "<secret>"}}]}}}'
```

Ref: https://docs.okd.io/latest/security/certificates/api-server.html

After the new API certifacate is active, the KUBECONFIG from installer
directeory stops working because the CA for the API certificate now is
different from the cluster issuer. After this you can use `oc login` with
the `kubeadmin` user. The password is in the same installer subdirectory
as the kubeconfig file

If the new API cert is from the staging environment it will also be invalid
(due to incomplete trust chain). This can be worked around like so:
```
function openshift_get_token {$
  if [ -z $1 ]$
  then$
    echo "Usage: $0  <clustername>.<domain>"$
  else$
    curl -u "kubeadmin:$(cat installer/auth/kubeadmin-password)" "https://oauth-openshift.apps.$1/oauth/authorize?client_id=openshift-challenging-client&response_type=token" -H "X-CSRF-Token: foobar" -skv  --stderr - | grep -oP "access_token=\K[^&]*"$
  fi$
}

$ oc login https://api.<cluster_name>.<domain>:6443 --insecure-skip-tls-verify=true --token="$(openshift_get_token <clustername>.<domain>)"
```

## Additional resources

Here is some more resources for background and/or alternate approaches.

* https://rcarrata.com/openshift/ocp4_renew_automatically_certificates/
* https://www.redhat.com/sysadmin/cert-manager-operator-openshift
* https://docs.openshift.com/container-platform/4.8/operators/admin/olm-adding-operators-to-cluster.html
* https://stackoverflow.com/questions/49501133/how-to-get-openshift-session-token-using-rest-api-calls
