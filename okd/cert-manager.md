oc create namespace cert-manager

oc get packagemanifests |grep cert-m


apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: cert-manager
  namespace: cert-manager


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


 kubectl create secret generic gandi-credentials \
     --namespace cert-manager --from-literal=api-token="$(cat ./gk)"
secret/gandi-credentials created

git clone https://github.com/bwolf/cert-manager-webhook-gandi.git

 helm install cert-manager-webhook-gandi \
     --namespace cert-manager \
     --set features.apiPriorityAndFairness=true \
     --set image.repository=bwolf/cert-manager-webhook-gandi \
     --set image.tag=latest \
     --set logLevel=2 \
     ./cert-manager-webhook-gandi/deploy/cert-manager-webhook-gandi

# Need to modify helm chart to let webhook listen to 8443 since 443 is not allowed by okd 

diff --git a/deploy/cert-manager-webhook-gandi/templates/deployment.yaml b/deploy/cert-manager-webhook-gandi/templates/deployment.yaml
index 073a61b..9761f72 100644
--- a/deploy/cert-manager-webhook-gandi/templates/deployment.yaml
+++ b/deploy/cert-manager-webhook-gandi/templates/deployment.yaml
@@ -26,6 +26,7 @@ spec:
           image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
           imagePullPolicy: {{ .Values.image.pullPolicy }}
           args:
+            - --secure-port=8443
             - --tls-cert-file=/tls/tls.crt
             - --tls-private-key-file=/tls/tls.key
 {{- if .Values.logLevel }}
@@ -36,7 +37,7 @@ spec:
               value: {{ .Values.groupName | quote }}
           ports:
             - name: https
-              containerPort: 443
+              containerPort: 8443
               protocol: TCP
           livenessProbe:
             httpGet:
diff --git a/deploy/cert-manager-webhook-gandi/templates/service.yaml b/deploy/cert-manager-webhook-gandi/templates/service.yaml
index 817c60c..8b4cea6 100644
--- a/deploy/cert-manager-webhook-gandi/templates/service.yaml
+++ b/deploy/cert-manager-webhook-gandi/templates/service.yaml
@@ -12,9 +12,9 @@ spec:
   type: {{ .Values.service.type }}
   ports:
     - port: {{ .Values.service.port }}
-      targetPort: https
+      targetPort: 8443
       protocol: TCP
       name: https
   selector:
     app: {{ include "cert-manager-webhook-gandi.name" . }}


# Cluster issuer
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

# Ingress cert
https://docs.okd.io/latest/security/certificates/replacing-default-ingress-certificate.html

apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: okd-apps-wildcard
  namespace: openshift-ingress
spec:
  dnsNames:
  - '*.apps.wip.saft.in'
  issuerRef:
    kind: ClusterIssuer
    name: letsencrypt-staging
  secretName: okd-apps-wildcard-tls

oc patch ingresscontroller.operator default --type=merge -p '{"spec":{"defaultCertificate": {"name": "okd-apps-wildcard-tls"}}}' -n openshift-ingress-operator


# API-server 

https://docs.okd.io/latest/security/certificates/api-server.html

 cat api-cert.yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: okd-api
  namespace: openshift-config
spec:
  dnsNames:
  - 'api.wip.saft.in'
  issuerRef:
    kind: ClusterIssuer
    name: letsencrypt-staging
  secretName: okd-api-tls


oc patch apiserver cluster --type=merge -p '{"spec":{"servingCerts": {"namedCertificates": [{"names": ["<FQDN>"], "servingCertificate": {"name": "<secret>"}}]}}}' 

