"""
Copyright 2014 Hewlett-Packard

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

import falcon
import logging

from freezer_api.common._i18n import _


class FreezerAPIException(falcon.HTTPError):
    """
    Base Freezer API Exception
    """
    message = "unknown error"

    def __init__(self, message=''):
        if message:
            self.message = _(str(message))
        logging.error(message)
        Exception.__init__(self, message)

    @staticmethod
    def handle(ex, req, resp, params):
        raise falcon.HTTPError(_('500 unknown server error'),
                               title=_("Internal Server Error"),
                               description=FreezerAPIException.message)


class BadDataFormat(FreezerAPIException):
    @staticmethod
    def handle(ex, req, resp, params):
        raise falcon.HTTPBadRequest(
            title=_("Bad request format"),
            description=ex.message)


class DocumentExists(FreezerAPIException):
    @staticmethod
    def handle(ex, req, resp, params):
        raise falcon.HTTPConflict(
            title=_("Document already existing"),
            description=ex.message)


class StorageEngineError(FreezerAPIException):
    @staticmethod
    def handle(ex, req, resp, params):
        raise falcon.HTTPInternalServerError(
            title=_("Internal Storage Error"),
            description=ex.message)


class DocumentNotFound(FreezerAPIException):
    @staticmethod
    def handle(ex, req, resp, params):
        raise falcon.HTTPNotFound(
            title=_("Not Found"),
            description=ex.message)


class AccessForbidden(FreezerAPIException):
    @staticmethod
    def handle(ex, req, resp, params):
        raise falcon.HTTPForbidden(
            title=_("Access Forbidden"),
            description=ex.message)


class MethodNotImplemented(FreezerAPIException):
    @staticmethod
    def handle(ex, req, resp, params):
        raise falcon.HTTPMethodNotAllowed(
            title=_("Bad Method"),
            description=ex.message)


exception_handlers_catalog = [
    BadDataFormat,
    DocumentExists,
    StorageEngineError,
    DocumentNotFound,
    AccessForbidden,
    MethodNotImplemented
]
