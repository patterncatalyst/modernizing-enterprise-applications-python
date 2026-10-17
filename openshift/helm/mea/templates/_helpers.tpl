{{/*
Common labels applied to every object, following the k8s recommended label
set the deploy/k8s/base manifests already use (app.kubernetes.io/part-of:
mea).
*/}}
{{- define "mea.labels" -}}
app.kubernetes.io/part-of: mea
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/*
In-cluster DNS suffix for the release namespace, e.g. mea.svc.cluster.local.
Used to build the cross-service URLs in the app ConfigMap, the Secret's
database-url, and Kafka's advertised listeners, so the chart works unchanged
in whatever namespace it is installed into.
*/}}
{{- define "mea.dns" -}}
{{ .Release.Namespace }}.svc.cluster.local
{{- end -}}
