"""
 Copyright 2022 SAP SE
 
 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at
 
     http://www.apache.org/licenses/LICENSE-2.0
 
 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""
import logging, kopf
from seeder_ccloud import utils
from seeder_ccloud.openstack.openstack_helper import OpenstackHelper

config = utils.Config()

@kopf.on.validate(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.bgpvpns')
def validate(spec, dryrun, **_):
    bgpvpns = spec.get('bgpvpns', [])
    for bgpvpn in bgpvpns:
        if 'name' not in bgpvpn or not bgpvpn['name']:
            raise kopf.AdmissionError("Router must have a name...")
        if isinstance(bgpvpn.get('import_targets', []), list):
            raise kopf.AdmissionError()
        if isinstance(bgpvpn.get('export_targets', []), list):
            raise kopf.AdmissionError()
        if isinstance(bgpvpn.get('route_targets', []), list):
            raise kopf.AdmissionError()



@kopf.on.update(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.bgpvpns')
@kopf.on.create(config.crd_info['plural'], annotations={'operatorVersion': config.operator_version}, field='spec.openstack.bgpvpns')
def seed_bgpvpns_handler(memo: kopf.Memo, new, old, name, annotations, **_):
    logging.info('seeding {} bgpvpns'.format(name))
    if not config.is_dependency_successful(annotations):
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, 'dependencies error'), delay=30)
    try:
        changed = utils.get_changed_seeds(old, new)
        Bgpvpns(memo['args'], memo['dry_run']).seed(changed)
    except Exception as error:
        raise kopf.TemporaryError('error seeding {}: {}'.format(name, error), delay=30)


class Bgpvpns():
    def __init__(self, args, dry_run=False):
        self.openstack = OpenstackHelper(args)
        self.dry_run = dry_run


    def seed(self, endpoints):
        for endpoint in endpoints:
            self._seed_bgpvpns(endpoint)


    def _seed_bgpvpn(self, bgpvpn):
        """
        seed a projects neutron BGPVPNs and dependent objects
        :param project: the project for which the resources are being created
        :param bgpvpns: the list of resources that sould be created
        """
        project_name = bgpvpn['project']
        project_id = self.openstack.get_project_id(bgpvpn['domain'], project_name)
        logging.debug("seeding bgpvpns of project %s" % project_name)

        # grab a neutron client
        neutron = self.openstack.get_neutronclient()

        try:
            bgpvpn = self.openstack.sanitize(bgpvpn, ('name', 'import_targets',
                                    'export_targets', 'route_targets'))

            body = {'bgpvpn': bgpvpn.copy()}
            body['bgpvpn']['tenant_id'] = project_id

            # check if the bgpvpn already exists
            query = {'tenant_id': project_id, 'name': bgpvpn['name']}
            result = neutron.list_bgpvpns(retrieve_all=True, **query)
            if not result or not result['bgpvpns']:
                logging.info(
                    "create bgpvpn '%s/%s'" % (project_name, bgpvpn['name']))
                result = neutron.create_bgpvpn(body)
                resource = result['bgpvpn']
            else:
                resource = result['bgpvpn'][0]
                for attr in list(bgpvpn.keys()):
                    if bgpvpn[attr] != resource.get(attr, ''):
                        logging.info(
                            "%s differs. update bgpvpn '%s/%s'" % (
                                attr, project_name, bgpvpn['name']))
                        # drop read-only attributes
                        body['bgpvpn'].pop('tenant_id', None)
                        neutron.update_bgpvpn(resource['id'], body)
                        break
        except Exception as e:
            logging.error("could not seed bgpvpn %s/%s: %s" % (
                project_name, bgpvpn['name'], e))
            raise
