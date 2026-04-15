{{/* vim: set filetype=mustache: */}}
{{/*
Construct the Keystone authentication URL base.
Uses global.clusterDomain if set, otherwise falls back to global.clusterDNSSearchDomain.
*/}}
{{define "keystone_url"}}{{ if .Values.global.clusterDomain }}http://keystone.{{ default .Release.Namespace .Values.global.keystoneNamespace }}.svc.{{.Values.global.clusterDomain}}:5000{{ else }}http://keystone.{{ default .Release.Namespace .Values.global.keystoneNamespace }}.svc.{{.Values.global.clusterDNSSearchDomain | required "missing value for .Values.global.clusterDNSSearchDomain"}}:5000{{end}}{{end}}
