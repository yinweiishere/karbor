# Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from karbor.context import RequestContext
from karbor.services.protection.clients import cinder

from karbor.tests import base
from oslo_config import cfg


class CinderClientTest(base.TestCase):
    def setUp(self):
        super(CinderClientTest, self).setUp()
        service_catalog = [
            {'type': 'volumev3',
             'name': 'cinderv3',
             'endpoints': [{'publicURL': 'http://127.0.0.1:8776/v3/abcd'}],
             },
        ]
        self._context = RequestContext(user_id='admin',
                                       project_id='abcd',
                                       auth_token='efgh',
                                       service_catalog=service_catalog)

    def test_create_client_by_endpoint(self):
        cfg.CONF.set_default('cinder_endpoint',
                             'http://127.0.0.1:8776/v3',
                             'cinder_client')
        client = cinder.create(self._context, cfg.CONF)
        self.assertEqual('volumev3', client.client.service_type)
        self.assertEqual('http://127.0.0.1:8776/v3/abcd',
                         client.client.management_url)

    def test_create_client_by_catalog(self):
        client = cinder.create(self._context, cfg.CONF)
        self.assertEqual('volumev3', client.client.service_type)
        self.assertEqual('http://127.0.0.1:8776/v3/abcd',
                         client.client.management_url)
