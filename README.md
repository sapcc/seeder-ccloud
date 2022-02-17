# CCloud Seeder

Seed the following ccloud content with a kubernetes operator.
- openstack

## operator
- introduces a new kubernetes CustomResourceDefinition **ccloudseeds**
    - **kubectl get ccloudseed** lists all deployed ccloud seeds
    - kubectl apply/delete can be used to maintain ccloud seed specs
- the k8s ccloud-seeder watches the lifecycle events of these specs
- currently the operator seeds openstack content
- ccloud seed specs can depend on another (hierarchy) 
- on a lifecycle event of a seed spec (only create/update), the operator checks,
  if all dependencies have been successfully seeded, only then it invokes the 
  seeding of the actual spec
- it uses the kopf k8s operator framework and uses handlers for the different entities
  in the seed spec.
  
Seeding currently only supports creating or updating of entities (upserts).  

## Supported entities

- openstack
    - regions
    - roles
    - role_inferences
    - rbac_policies
    - services
        - endpoints
    - flavors
        - extra-specs
    - share_types
        - is_public
        - specs
            - driver_handles_share_servers
            - snapshot_support
        - extra-specs
    - domains
        - configuration
    - projects
    - project-endpoints
    - network quotas
    - address scopes
        - subnet pools
    - subnet pools
    - networks
        - tags
        - subnets
    - routers
    - projects
        - interfaces
        - dns_quota
        - dns_tsigkeys
        - ec2_creds
        - flavors
        - share_types
    - dns_zones
        - recordsets
    - groups
    - role-assignments
    - users
    - roles
    - swift 
        - account
        - containers
       
    
## Spec format
    
The seeding content can be provided in the usual kubernets spec yaml format.  
    
Example seed spec of a keystone seed to be deployed via helm:
    
    apiVersion: "seeder.cloud.sap/v1"
    kind: "CcloudSeed"
    metadata:
      name: keystone-seed
      labels:
        app: {{ template "fullname" . }}
        chart: "{{ .Chart.Name }}-{{ .Chart.Version }}"
        release: "{{ .Release.Name }}"
        heritage: "{{ .Release.Service }}"
    spec:
      roles:
      - name: admin
        description: 'Keystone Administration'
      - name: member
        description: 'Keystone Member'
      - name: reader
        description: 'Keystone Read-Only'
      - name: service
        description: 'Keystone Service'
    
      role_inferences:
      - prior_role: admin
        implied_role: member
        
      regions:
      - id: eu
        description: 'Europe'
      - id: staging
        description: 'Staging'
        parent_region_id: eu
      - id: qa
        description: 'QA'
        parent_region_id: eu
      - id: local
        description: 'Local Development'
    
      services:
      - name: keystone
        type: identity
        description: Openstack Identity
        endpoints:
        - region: local
          interface: public
          url: {{ .Value.keystoneUrl }}:5000/v3
          enabled: true
        - region: local
          interface: admin
          url: {{ .Value.keystoneUrl }}:35357/v3
          enabled: true
        - region: local
          interface: internal
          url: http://keystone.{{.Release.Namespace}}.svc.kubernetes.{{.Values.region}}.{{.Values.tld}}:5000/v3'
          enabled: false
    
      domains:
      - name: Default
        id: default
        description: Openstack Internal Domain
        enabled: true
      
      users:
      - name: admin
        description: Openstack Cloud Administrator
        enabled: true
        password: secret123
        role_assignments:
        - domain: Default
        role: admin
        - project: admin
        role: admin
        - project: service
        role: admin

      groups:
      - name: administrators
        description: Administrators
        role_assignments:
        - domain: Default
        role: admin
        - project: admin
        role: admin
        - project: service
        role: admin
        users:
        - admin
      - name: members
        description: Members
        role_assignments:
        - domain: Default
        role: member
    
      projects:
      - name: admin
        description: Administrator Project
      - name: service
        description: Services Project