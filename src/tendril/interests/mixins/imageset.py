

import os
import asyncio
from asgiref.sync import async_to_sync

from httpx import HTTPStatusError

from tendril.filestore import buckets
from tendril.config import IMAGESET_UPLOAD_FILESTORE_BUCKET
from tendril.config import IMAGESET_PUBLISHING_FILESTORE_BUCKET

from tendril.interests.mixins.base import InterestMixinBase
from tendril.common.states import LifecycleStatus
from tendril.authz.roles.interests import require_state
from tendril.authz.roles.interests import require_permission

from tendril.caching import tokens
from tendril.caching.tokens import TokenStatus

from tendril.db.controllers.imageset import create_imageset
from tendril.db.controllers.imageset import imageset_add_content
from tendril.db.controllers.imageset import imageset_remove_content
from tendril.db.controllers.imageset import imageset_heal_positions
from tendril.filestore.db.controller import get_storedfile_owner

from tendril.utils.parsers.media.info import get_media_info

from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class InterestImageSetMixin(InterestMixinBase):
    token_namespace = 'isu'
    upload_bucket_name = IMAGESET_UPLOAD_FILESTORE_BUCKET
    publish_bucket_name = IMAGESET_PUBLISHING_FILESTORE_BUCKET

    def __init__(self, *args, **kwargs):
        # TODO This never seems to get called. Figure out why.
        super(InterestImageSetMixin, self).__init__(*args, **kwargs)

    @property
    def imageset(self):
        return self.model_instance.imageset

    @with_db
    def activate(self, background_tasks=None, auth_user=None, session=None):
        result, msg = super().activate(background_tasks=background_tasks,
                                       auth_user=auth_user, session=session)

        if not self.model_instance.status == LifecycleStatus.ACTIVE:
            return result, msg

        publishable = self.publishable()

        if background_tasks:
            background_tasks.add_task(self._publish_files, publishable)
        else:
            asyncio.ensure_future(self._publish_files(publishable))
        return result, msg

    # TODO This may collide with other mixins. Improve superstructure. Perhaps a publishable mixin?
    async def _publish_files(self, stored_files):
        for stored_file in stored_files:
            logger.info(f"Publishing file {stored_file.filename}")
            try:
                upload_response = await self.upload_bucket.move(
                    filename=stored_file.filename,
                    target_bucket=self.publish_bucket_name,
                    actual_user=None,
                )
            except HTTPStatusError as e:
                self._report_filestore_error(None, e, "Publishing imageset file")
                continue

    # TODO This may collide with other mixins. Improve superstructure or standardize. Perhaps a publishable mixin?
    def publishable(self):
        rv = []
        for content in self.model_instance.imageset.contents:
            if content.storedfile.bucket.name == self.upload_bucket_name:
                rv.append(content.storedfile)
        return rv

    # TODO This may collide with other mixins. Improve superstructure or standardize. Perhaps a publishable mixin?
    def published(self):
        if self.status != LifecycleStatus.ACTIVE:
            return False
        for content in self.model_instance.imageset.contents:
            if content.storedfile.bucket.name != self.publish_bucket_name:
                return False
        return True

    @with_db
    def _commit_to_db(self, must_create=False, can_create=True, session=None):
        super(InterestImageSetMixin, self)._commit_to_db(must_create=must_create,
                                                         can_create=can_create,
                                                         session=session)
        if not self.model_instance.imageset_id:
            imageset = create_imageset(session=session)
            self.model_instance.imageset_id = imageset.id
            session.add(self.model_instance)
            session.commit()
            session.flush()

    # TODO This may collide with other mixins. Improve superstructure or standardize. Maybe a filestore integration mixin?
    @property
    def upload_bucket(self):
        if not hasattr(self, '_upload_bucket'):
            self._upload_bucket = None
        if not self._upload_bucket:
            self._upload_bucket = buckets.get_bucket(self.upload_bucket_name)
        return self._upload_bucket

    # TODO This may collide with other mixins. Improve superstructure or standardize. Maybe a filestore integration mixin?
    @property
    def publish_bucket(self):
        if not hasattr(self, '_publish_bucket'):
            self._publish_bucket = None
        if not self._publish_bucket:
            self._publish_bucket = buckets.get_bucket(self.publish_bucket_name)
        return self._publish_bucket

    # TODO Standardize. We're also using this in device_content. Maybe a filestore integration mixin?
    def _report_filestore_error(self, token_id, e, action_comment):
        logger.warn(f"Exception while {action_comment} : HTTP {e.response.status_code} {e.response.text}")
        if token_id:
            tokens.update(
                self.token_namespace, token_id, state=TokenStatus.FAILED,
                error={"summary": f"Exception while {action_comment}",
                       "filestore": {
                           "code": e.response.status_code,
                           "content": e.response.json()}
                       }
            )

    @with_db
    @require_state((LifecycleStatus.NEW, LifecycleStatus.APPROVAL, LifecycleStatus.ACTIVE))
    @require_permission('add_artefact', strip_auth=False)
    def upload_imageset_content(self, file, rename_to=None, token_id=None, auth_user=None, session=None):
        storage_folder = f'{self.id}'
        if token_id:
            tokens.update(self.token_namespace, token_id,
                          state=TokenStatus.INPROGRESS, max=3,
                          current="Parsing File Information")

        # 1. Parse Media Information
        filename = rename_to or file.filename
        media_info = get_media_info(file.file, filename=filename, original_filename=file.filename)

        if token_id:
            tokens.update(self.token_namespace, token_id,
                          current="Uploading File to Filestore", done=1)

        # 2. Upload File to Bucket
        # TODO This should add a label or title to the storedfile entry. This will need
        #  the filestore code to be edited to use the existing label field on artefact.
        #  We're currently forcing a prefix on the filename, which is a little ugly.
        try:
            upload_response = async_to_sync(self.upload_bucket.upload)(
                file=(os.path.join(storage_folder, filename), file.file),
                actual_user=auth_user.id, interest=self.id
            )
        except HTTPStatusError as e:
            self._report_filestore_error(token_id, e, "uploading imageset file to bucket")
            return

        if token_id:
            tokens.update(self.token_namespace, token_id, done=2,
                          current="Linking File to Imageset",
                          metadata={'storedfile_id': upload_response['storedfileid']})

        self.imageset_add(upload_response['storedfileid'], auth_user=auth_user, session=session)

        if token_id:
            tokens.update(self.token_namespace, token_id, current="Finishing", done=3)

        # 7. Close Upload Ticket
        tokens.close(self.token_namespace, token_id)

    @with_db
    @require_state((LifecycleStatus.NEW, LifecycleStatus.APPROVAL, LifecycleStatus.ACTIVE))
    @require_permission('add_artefact', strip_auth=False)
    def imageset_set_default_duration(self, default_duration=10, auth_user=None, session=None):

        if not isinstance(default_duration, int) or default_duration <= 0:
            raise ValueError("Expecting a positive integer for duration")

        self.model_instance.imageset.default_duration = default_duration
        session.add(self.model_instance.imageset)
        session.flush()
        return {'interest_id': self.id,
                'default_duration': self.model_instance.imageset.default_duration}

    @with_db
    @require_state((LifecycleStatus.NEW, LifecycleStatus.APPROVAL, LifecycleStatus.ACTIVE))
    @require_permission('edit', strip_auth=False)
    def imageset_set_colors(self, bgcolor, color, auth_user=None, session=None):
        self.model_instance.imageset.bgcolor = bgcolor
        self.model_instance.imageset.color = color
        session.add(self.model_instance.imageset)
        session.flush()
        return {'interest_id': self.id,
                'bgcolor': self.model_instance.imageset.bgcolor,
                'color': self.model_instance.imageset.color}

    @with_db
    @require_state((LifecycleStatus.NEW, LifecycleStatus.APPROVAL, LifecycleStatus.ACTIVE))
    @require_permission('read', strip_auth=False)
    def imageset_get_available_contents(self, auth_user=None, session=None):
        # TODO Use artefacts instead and filter by label. Presently, files not
        #  in the current imageset will not be shown.
        #  Also consider using the filename prefix in the interim to do this.
        #  get_stored_files might be able to get the job done, though you will need
        #  to check on both the upload and publish buckets. Alternatively, a direct
        #  query on the database might be easier. Filter on interest id and then
        #  on filename.
        contents = self.model_instance.imageset.contents
        contents = [{x.export()} for x in contents]

        return {'interest_id': self.id,
                'default_duration': self.model_instance.content.default_duration,
                'contents': contents}

    @with_db
    @require_state((LifecycleStatus.NEW, LifecycleStatus.APPROVAL, LifecycleStatus.ACTIVE))
    @require_permission('read', strip_auth=False)
    def imageset_get_contents(self, auth_user=None, session=None):
        contents = self.model_instance.imageset.contents
        contents = [x.export() for x in contents]

        return {'interest_id': self.id,
                'default_duration': self.model_instance.imageset.default_duration,
                'bgcolor': self.model_instance.imageset.bgcolor,
                'color': self.model_instance.imageset.color,
                'contents': contents}

    @with_db
    @require_state((LifecycleStatus.NEW, LifecycleStatus.APPROVAL, LifecycleStatus.ACTIVE))
    @require_permission('add_artefact', strip_auth=False)
    def imageset_add(self, storedfile_id, position=None, duration=None, auth_user=None, session=None):
        # Get Content and Verify Access
        owner = get_storedfile_owner(storedfile_id, session=session)
        if not owner['interest'].id == self.id:
            raise PermissionError(f"StoredFile {storedfile_id} does not seem to belong to this interest {self.id}. "
                                  "Cannot add to imageset.")

        if not duration:
            _duration = self.model_instance.imageset.default_duration

        # Create and commit Association Model
        imageset_add_content(id=self.model_instance.imageset_id,
                             storedfile=storedfile_id,
                             position=position,
                             duration=duration,
                             session=session)

        imageset_heal_positions(id=self.model_instance.imageset_id, session=session)
        return True

    @with_db
    @require_state((LifecycleStatus.NEW, LifecycleStatus.ACTIVE, LifecycleStatus.APPROVAL))
    @require_permission('add_artefact', strip_auth=False)
    def imageset_remove(self, position=None, auth_user=None, session=None):
        imageset_remove_content(id=self.model_instance.imageset_id,
                                position=position,
                                session=session)
        imageset_heal_positions(id=self.model_instance.imageset_id, session=session)
        # TODO Remove storedfile as well.
        return True
