"""
Copyright 2015 Hewlett-Packard

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

This product includes cryptographic software written by Eric Young
(eay@cryptsoft.com). This product includes software written by Tim
Hudson (tjh@cryptsoft.com).
========================================================================
"""

import elasticsearch

import logging
import uuid

from freezer_api.common._i18n import _, _LI
from freezer_api.common.utils import BackupMetadataDoc
from freezer_api.common.utils import JobDoc
from freezer_api.common.utils import ActionDoc
from freezer_api.common.utils import SessionDoc
from freezer_api.common import exceptions as freezer_api_exc


class TypeManager:
    def __init__(self, es, doc_type, index):
        self.es = es
        self.index = index
        self.doc_type = doc_type

    @staticmethod
    def get_base_search_filter(user_id, search=None):
        search = search or {}
        user_id_filter = {"term": {"user_id": user_id}}
        base_filter = [user_id_filter]
        match_list = [{"match": m} for m in search.get('match', [])]
        match_not_list = [{"match": m} for m in search.get('match_not', [])]
        base_filter.append({"query": {"bool": {"must": match_list,
                                               "must_not": match_not_list}}})
        return base_filter

    @staticmethod
    def get_search_query(user_id, doc_id, search=None):
        search = search or {}
        try:
            base_filter = TypeManager.get_base_search_filter(user_id, search)
            query_filter = {"filter": {"bool": {"must": base_filter}}}
            return {'query': {'filtered': query_filter}}
        except:
            raise freezer_api_exc.StorageEngineError(
                message=_('search operation failed: query not valid'))

    def get(self, user_id, doc_id):
        try:
            res = self.es.get(index=self.index,
                              doc_type=self.doc_type,
                              id=doc_id)
            doc = res['_source']
        except elasticsearch.TransportError:
            raise freezer_api_exc.DocumentNotFound(
                message=_('No document found with ID %s') % doc_id)
        except Exception as e:
            raise freezer_api_exc.StorageEngineError(
                message=_('Get operation failed: %s') % e)
        if doc['user_id'] != user_id:
            raise freezer_api_exc.AccessForbidden(
                _("Document access forbidden"))
        if '_version' in res:
            doc['_version'] = res['_version']
        return doc

    def search(self, user_id, doc_id=None, search=None, offset=0, limit=10):
        search = search or {}
        query_dsl = self.get_search_query(user_id, doc_id, search)
        try:
            res = self.es.search(index=self.index, doc_type=self.doc_type,
                                 size=limit, from_=offset, body=query_dsl)
        except elasticsearch.ConnectionError:
            raise freezer_api_exc.StorageEngineError(
                message=_('unable to connect to db server'))
        except Exception as e:
            raise freezer_api_exc.StorageEngineError(
                message=_('search operation failed: %s') % e)
        hit_list = res['hits']['hits']
        return [x['_source'] for x in hit_list]

    def insert(self, doc, doc_id=None):
        version = doc.pop('_version', 0)
        try:
            res = self.es.index(index=self.index, doc_type=self.doc_type,
                                body=doc, id=doc_id, version=version)
            created = res['created']
            version = res['_version']
        except elasticsearch.TransportError as e:
            if e.status_code == 409:
                raise freezer_api_exc.DocumentExists(message=e.error)
            raise freezer_api_exc.StorageEngineError(
                message=_('index operation failed %s') % e)
        except Exception as e:
            raise freezer_api_exc.StorageEngineError(
                message=_('index operation failed %s') % e)
        return (created, version)

    def delete(self, user_id, doc_id):
        query_dsl = self.get_search_query(user_id, doc_id)
        try:
            self.es.delete_by_query(index=self.index,
                                    doc_type=self.doc_type,
                                    body=query_dsl)
        except Exception as e:
            raise freezer_api_exc.StorageEngineError(
                message=_('Delete operation failed: %s') % e)
        return doc_id


class BackupTypeManager(TypeManager):
    def __init__(self, es, doc_type, index='freezer'):
        TypeManager.__init__(self, es, doc_type, index=index)

    @staticmethod
    def get_search_query(user_id, doc_id, search=None):
        search = search or {}
        base_filter = TypeManager.get_base_search_filter(user_id, search)
        if doc_id is not None:
            base_filter.append({"term": {"backup_id": doc_id}})

        if 'time_after' in search:
            base_filter.append(
                {"range": {"timestamp": {"gte": int(search['time_after'])}}}
            )

        if 'time_before' in search:
            base_filter.append(
                {"range": {"timestamp": {"lte": int(search['time_before'])}}}
            )
        query_filter = {"filter": {"bool": {"must": base_filter}}}
        return {'query': {'filtered': query_filter}}


class ClientTypeManager(TypeManager):
    def __init__(self, es, doc_type, index='freezer'):
        TypeManager.__init__(self, es, doc_type, index=index)

    @staticmethod
    def get_search_query(user_id, doc_id, search=None):
        search = search or {}
        base_filter = TypeManager.get_base_search_filter(user_id, search)
        if doc_id is not None:
            base_filter.append({"term": {"client_id": doc_id}})
        query_filter = {"filter": {"bool": {"must": base_filter}}}
        return {'query': {'filtered': query_filter}}


class JobTypeManager(TypeManager):
    def __init__(self, es, doc_type, index='freezer'):
        TypeManager.__init__(self, es, doc_type, index=index)

    @staticmethod
    def get_search_query(user_id, doc_id, search=None):
        search = search or {}
        base_filter = TypeManager.get_base_search_filter(user_id, search)
        if doc_id is not None:
            base_filter.append({"term": {"job_id": doc_id}})
        query_filter = {"filter": {"bool": {"must": base_filter}}}
        return {'query': {'filtered': query_filter}}

    def update(self, job_id, job_update_doc):
        version = job_update_doc.pop('_version', 0)
        update_doc = {"doc": job_update_doc}
        try:
            res = self.es.update(index=self.index, doc_type=self.doc_type,
                                 id=job_id, body=update_doc, version=version)
            version = res['_version']
        except elasticsearch.TransportError as e:
            if e.status_code == 409:
                raise freezer_api_exc.DocumentExists(message=e.error)
            raise freezer_api_exc.DocumentNotFound(
                message=_('Unable to find job to update '
                          'with id %(id)s. %(e)s') % {'id': job_id, 'e': e})
        except Exception:
            raise freezer_api_exc.StorageEngineError(
                message=_('Unable to update job with id %s') % job_id)
        return version


class ActionTypeManager(TypeManager):
    def __init__(self, es, doc_type, index='freezer'):
        TypeManager.__init__(self, es, doc_type, index=index)

    @staticmethod
    def get_search_query(user_id, doc_id, search=None):
        search = search or {}
        base_filter = TypeManager.get_base_search_filter(user_id, search)
        if doc_id is not None:
            base_filter.append({"term": {"action_id": doc_id}})
        query_filter = {"filter": {"bool": {"must": base_filter}}}
        return {'query': {'filtered': query_filter}}

    def update(self, action_id, action_update_doc):
        version = action_update_doc.pop('_version', 0)
        update_doc = {"doc": action_update_doc}
        try:
            res = self.es.update(index=self.index, doc_type=self.doc_type,
                                 id=action_id, body=update_doc,
                                 version=version)
            version = res['_version']
        except elasticsearch.TransportError as e:
            if e.status_code == 409:
                raise freezer_api_exc.DocumentExists(message=e.error)
            raise freezer_api_exc.DocumentNotFound(
                message=_('Unable to find action to update '
                          'with id %s') % action_id)
        except Exception:
            raise freezer_api_exc.StorageEngineError(
                message=_('Unable to update action with id %s') % action_id)
        return version


class SessionTypeManager(TypeManager):
    def __init__(self, es, doc_type, index='freezer'):
        TypeManager.__init__(self, es, doc_type, index=index)

    @staticmethod
    def get_search_query(user_id, doc_id, search=None):
        search = search or {}
        base_filter = TypeManager.get_base_search_filter(user_id, search)
        if doc_id is not None:
            base_filter.append({"term": {"session_id": doc_id}})
        query_filter = {"filter": {"bool": {"must": base_filter}}}
        return {'query': {'filtered': query_filter}}

    def update(self, session_id, session_update_doc):
        version = session_update_doc.pop('_version', 0)
        update_doc = {"doc": session_update_doc}
        try:
            res = self.es.update(index=self.index, doc_type=self.doc_type,
                                 id=session_id, body=update_doc,
                                 version=version)
            version = res['_version']
        except elasticsearch.TransportError as e:
            if e.status_code == 409:
                raise freezer_api_exc.DocumentExists(message=e.error)
            raise freezer_api_exc.DocumentNotFound(
                message=_(('Unable to update session '
                           '%s. %s') % (session_id, e)))

        except Exception:
            raise freezer_api_exc.StorageEngineError(
                message=_('Unable to update session with id %s') % session_id)
        return version


class ElasticSearchEngine(object):

    def __init__(self, hosts, index='freezer'):
        self.index = index
        self.es = elasticsearch.Elasticsearch(hosts)
        logging.info(_LI('Using Elasticsearch host %s') % hosts)
        self.backup_manager = BackupTypeManager(self.es, 'backups')
        self.client_manager = ClientTypeManager(self.es, 'clients')
        self.job_manager = JobTypeManager(self.es, 'jobs')
        self.action_manager = ActionTypeManager(self.es, 'actions')
        self.session_manager = SessionTypeManager(self.es, 'sessions')

    def get_backup(self, user_id, backup_id=None,
                   offset=0, limit=10, search=None):
        search = search or {}
        return self.backup_manager.search(user_id,
                                          backup_id,
                                          search=search,
                                          offset=offset,
                                          limit=limit)

    def add_backup(self, user_id, user_name, doc):
        # raises if data is malformed (HTTP_400) or already present (HTTP_409)
        backup_metadata_doc = BackupMetadataDoc(user_id, user_name, doc)
        if not backup_metadata_doc.is_valid():
            raise freezer_api_exc.BadDataFormat(message=_('Bad Data Format'))
        backup_id = backup_metadata_doc.backup_id
        existing = self.backup_manager.search(user_id, backup_id)
        if existing:
            raise freezer_api_exc.DocumentExists(
                message=_('Backup data already existing with ID %s') %
                backup_id)
        self.backup_manager.insert(backup_metadata_doc.serialize())
        return backup_id

    def delete_backup(self, user_id, backup_id):
        return self.backup_manager.delete(user_id, backup_id)

    def get_client(self, user_id, client_id=None,
                   offset=0, limit=10, search=None):
        search = search or {}
        return self.client_manager.search(user_id,
                                          client_id,
                                          search=search,
                                          offset=offset,
                                          limit=limit)

    def add_client(self, user_id, doc):
        client_id = doc.get('client_id', None)
        if client_id is None:
            raise freezer_api_exc.BadDataFormat(message=_('Missing client ID'))
        existing = self.client_manager.search(user_id, client_id)
        if existing:
            raise freezer_api_exc.DocumentExists(
                message=_('Client already registered with ID %s') % client_id)
        client_doc = {'client': doc,
                      'user_id': user_id,
                      'uuid': uuid.uuid4().hex}
        self.client_manager.insert(client_doc)
        logging.info(_LI('Client registered, client_id: %s') % client_id)
        return client_id

    def delete_client(self, user_id, client_id):
        return self.client_manager.delete(user_id, client_id)

    def get_job(self, user_id, job_id):
        return self.job_manager.get(user_id, job_id)

    def search_job(self, user_id, offset=0, limit=10, search=None):
        search = search or {}
        return self.job_manager.search(user_id,
                                       search=search,
                                       offset=offset,
                                       limit=limit)

    def add_job(self, user_id, doc):
        jobdoc = JobDoc.create(doc, user_id)
        job_id = jobdoc['job_id']
        self.job_manager.insert(jobdoc, job_id)
        logging.info(_LI('Job registered, job id: %s') % job_id)
        return job_id

    def delete_job(self, user_id, job_id):
        return self.job_manager.delete(user_id, job_id)

    def update_job(self, user_id, job_id, patch_doc):
        valid_patch = JobDoc.create_patch(patch_doc)

        # check that document exists
        assert (self.job_manager.get(user_id, job_id))

        version = self.job_manager.update(job_id, valid_patch)
        logging.info(_LI('Job %(id)s updated to version %(version)s') %
                     {'id': job_id, 'version': version})
        return version

    def replace_job(self, user_id, job_id, doc):
        # check that no document exists with
        # same job_id and different user_id
        try:
            self.job_manager.get(user_id, job_id)
        except freezer_api_exc.DocumentNotFound:
            pass

        valid_doc = JobDoc.update(doc, user_id, job_id)

        (created, version) = self.job_manager.insert(valid_doc, job_id)
        if created:
            logging.info(_LI('Job %s created') % job_id)
        else:
            logging.info(_LI('Job %(id)s replaced with version %(version)s' %
                         {'id': job_id, 'version': version}))
        return version

    def get_action(self, user_id, action_id):
        return self.action_manager.get(user_id, action_id)

    def search_action(self, user_id, offset=0, limit=10, search=None):
        search = search or {}
        return self.action_manager.search(user_id,
                                          search=search,
                                          offset=offset,
                                          limit=limit)

    def add_action(self, user_id, doc):
        actiondoc = ActionDoc.create(doc, user_id)
        action_id = actiondoc['action_id']
        self.action_manager.insert(actiondoc, action_id)
        logging.info(_LI('Action registered, action id: %s') % action_id)
        return action_id

    def delete_action(self, user_id, action_id):
        return self.action_manager.delete(user_id, action_id)

    def update_action(self, user_id, action_id, patch_doc):
        valid_patch = ActionDoc.create_patch(patch_doc)

        # check that document exists
        assert (self.action_manager.get(user_id, action_id))

        version = self.action_manager.update(action_id, valid_patch)
        logging.info(_LI('Action %(id)s updated to version %(version)s' %
                     {'id': action_id, 'version': version}))
        return version

    def replace_action(self, user_id, action_id, doc):
        # check that no document exists with
        # same action_id and different user_id
        try:
            self.action_manager.get(user_id, action_id)
        except freezer_api_exc.DocumentNotFound:
            pass

        valid_doc = ActionDoc.update(doc, user_id, action_id)

        (created, version) = self.action_manager.insert(valid_doc, action_id)
        if created:
            logging.info(_LI('Action %s created') % action_id)
        else:
            logging.info(_LI('Action %(id)s replaced with version %(version)s'
                         % {'id': action_id, 'version': version}))
        return version

    def get_session(self, user_id, session_id):
        return self.session_manager.get(user_id, session_id)

    def search_session(self, user_id, offset=0, limit=10, search=None):
        search = search or {}
        return self.session_manager.search(user_id,
                                           search=search,
                                           offset=offset,
                                           limit=limit)

    def add_session(self, user_id, doc):
        session_doc = SessionDoc.create(doc, user_id)
        session_id = session_doc['session_id']
        self.session_manager.insert(session_doc, session_id)
        logging.info(_LI('Session registered, session id: %s') % session_id)
        return session_id

    def delete_session(self, user_id, session_id):
        return self.session_manager.delete(user_id, session_id)

    def update_session(self, user_id, session_id, patch_doc):
        valid_patch = SessionDoc.create_patch(patch_doc)

        # check that document exists
        assert (self.session_manager.get(user_id, session_id))

        version = self.session_manager.update(session_id, valid_patch)
        logging.info(_LI('Session %(id)s updated to version %(version)s' %
                     {'id': session_id, 'version': version}))
        return version

    def replace_session(self, user_id, session_id, doc):
        # check that no document exists with
        # same session_id and different user_id
        try:
            self.session_manager.get(user_id, session_id)
        except freezer_api_exc.DocumentNotFound:
            pass

        valid_doc = SessionDoc.update(doc, user_id, session_id)

        (created, version) = self.session_manager.insert(valid_doc, session_id)
        if created:
            logging.info(_LI('Session %s created') % session_id)
        else:
            logging.info(_LI('Session %(id)s replaced with version %(version)s'
                         % {'id': session_id, 'version': version}))
        return version
