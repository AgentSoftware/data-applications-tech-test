{{/*
Expand the name of the chart.
*/}}
{{- define "psc-pipeline.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "psc-pipeline.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "psc-pipeline.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "psc-pipeline.labels" -}}
helm.sh/chart: {{ include "psc-pipeline.chart" . }}
{{ include "psc-pipeline.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "psc-pipeline.selectorLabels" -}}
app.kubernetes.io/name: {{ include "psc-pipeline.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "psc-pipeline.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "psc-pipeline.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
PostgreSQL host: database.host, or the bundled subchart's Service (same naming rule as its "postgres.fullname").
*/}}
{{- define "psc-pipeline.dbHost" -}}
{{- if .Values.database.host }}
{{- .Values.database.host }}
{{- else if not .Values.postgres.enabled }}
{{- fail "set database.host when postgres.enabled is false" }}
{{- else if contains "postgres" .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-postgres" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Connection settings as libpq PG* variables. The password comes from the Secret, never a ConfigMap or URL.
*/}}
{{- define "psc-pipeline.dbEnv" -}}
- name: PGHOST
  value: {{ include "psc-pipeline.dbHost" . | quote }}
- name: PGPORT
  value: {{ .Values.database.port | quote }}
- name: PGDATABASE
  valueFrom: {secretKeyRef: {name: {{ .Values.database.secretName }}, key: POSTGRES_DB}}
- name: PGUSER
  valueFrom: {secretKeyRef: {name: {{ .Values.database.secretName }}, key: USERDB_USER}}
- name: PGPASSWORD
  valueFrom: {secretKeyRef: {name: {{ .Values.database.secretName }}, key: USERDB_PASSWORD}}
{{- end }}
