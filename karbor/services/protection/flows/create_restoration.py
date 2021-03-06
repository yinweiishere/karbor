# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_config import cfg
from oslo_log import log as logging
from oslo_service import loopingcall
from oslo_utils import uuidutils

from karbor.common import constants
from karbor.i18n import _LE, _LI
from karbor.services.protection.client_factory import ClientFactory
from karbor.services.protection.restore_heat import HeatTemplate
from taskflow import task

sync_status_opts = [
    cfg.IntOpt('sync_status_interval',
               default=60,
               help='update protection status interval')
]

CONF = cfg.CONF
CONF.register_opts(sync_status_opts)

LOG = logging.getLogger(__name__)


class CreateStackTask(task.Task):
    def __init__(self, heat_client, template):
        provides = 'stack_id'
        super(CreateStackTask, self).__init__(provides=provides)
        self._heat_client = heat_client
        self._template = template

    def execute(self):
        stack_name = "restore_%s" % uuidutils.generate_uuid()
        LOG.info(_LI("creating stack, stack_name:%s"), stack_name)
        try:
            body = self._heat_client.stacks.create(
                stack_name=stack_name,
                template=self._template.to_dict())
            return body['stack']['id']
        except Exception:
            LOG.error(_LE("use heat to create stack failed"))
            raise


class SyncStackStatusTask(task.Task):
    def __init__(self, checkpoint, heat_client, restore):
        requires = ['stack_id']
        super(SyncStackStatusTask, self).__init__(requires=requires)
        self._heat_client = heat_client
        self._checkpoint = checkpoint
        self._restore = restore

    def execute(self, stack_id):
        LOG.info(_LI("syncing stack status, stack_id: %s"), stack_id)
        sync_status_loop = loopingcall.FixedIntervalLoopingCall(
            self._sync_status, self._checkpoint, stack_id)
        sync_status_loop.start(interval=CONF.sync_status_interval)

    def _sync_status(self, checkpoint, stack_id):
        try:
            stack = self._heat_client.stacks.get(stack_id)
            stack_status = getattr(stack, 'stack_status')
            if stack_status == 'CREATE_IN_PROGRESS':
                return

            if stack_status == 'CREATE_FAILED':
                status = constants.OPERATION_EXE_STATE_FAILED
            elif stack_status == 'CREATE_COMPLETE':
                status = constants.OPERATION_EXE_STATE_SUCCESS

            status_dict = {
                "status": status
            }
            self._restore.update(status_dict)
            self._restore.save()
            raise loopingcall.LoopingCallDone()
        except Exception:
            LOG.info(_LI("stop sync stack status, stack_id: %s"), stack_id)
            raise


def get_flow(context, workflow_engine, operation_type, checkpoint, provider,
             restore, restore_auth):
    target = restore.get('restore_target', None)

    # TODO(luobin): create a heat_client
    # Initialize a heat client using current login tenant when the
    # restore_target and restore_auth is not provided.
    if target is not None:
        username = None
        password = None
        if restore_auth is not None:
            auth_type = restore_auth.get("type", None)
            if auth_type == "password":
                username = restore_auth["username"]
                password = restore_auth["password"]
        kwargs = {"auth_url": target,
                  "username": username,
                  "password": password}
    else:
        kwargs = {}
    heat_client = ClientFactory.create_client("heat",
                                              context=context,
                                              **kwargs)

    # TODO(luobin): create a heat_template
    heat_template = HeatTemplate()

    ctx = {'context': context,
           'checkpoint': checkpoint,
           'workflow_engine': workflow_engine,
           'operation_type': operation_type,
           'restore': restore,
           'heat_template': heat_template}

    flow_name = "create_restoration_" + checkpoint.id
    restoration_flow = workflow_engine.build_flow(flow_name, 'linear')
    result = provider.build_task_flow(ctx)
    resource_flow = result.get('task_flow')
    workflow_engine.add_tasks(
        restoration_flow,
        resource_flow,
        CreateStackTask(heat_client, heat_template),
        SyncStackStatusTask(checkpoint, heat_client, restore)
    )
    flow_engine = workflow_engine.get_engine(restoration_flow)
    return flow_engine
