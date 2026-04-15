{{/* vim: set filetype=mustache: */}}
{{/*
Construct the Keystone authentication URL base.
Uses global.clusterDomain if set, otherwise falls back to global.clusterDNSSearchDomain.
*/}}
{{define "keystone_url"}}http://keystone.{{ default .Release.Namespace .Values.global.keystoneNamespace }}.svc.{{ if .Values.global.clusterDomain }}{{.Values.global.clusterDomain}}{{ else }}{{.Values.global.clusterDNSSearchDomain | required "missing value for .Values.global.clusterDNSSearchDomain"}}{{end}}:5000{{end}}
