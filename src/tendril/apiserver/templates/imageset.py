

import os
import uuid
from typing import Dict
from typing import Union
from typing import Optional
from pydantic.fields import Field
from inflection import singularize
from inflection import titleize

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends
from fastapi import File
from fastapi import Body
from fastapi import UploadFile
from fastapi import BackgroundTasks

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.apiserver.templates.base import ApiRouterGenerator
from tendril.utils.pydantic import TendrilTORMModel
from tendril.utils.pydantic import TendrilTBaseModel
from tendril.utils.db import get_session

from tendril.caching import tokens
from tendril.caching.tokens import GenericTokenTModel

from tendril.structures.content import content_models
from tendril.config import IMAGESET_EXTENSIONS
from tendril.interests.mixins.imageset import InterestImageSetMixin
from tendril.common.imageset.exceptions import FileTypeUnsupported
from tendril.db.models.content_formats import MediaContentFormatInfoTModel
from tendril.db.models.content_formats import MediaContentFormatInfoFullTModel
from tendril.db.models.content import MediaContentInfoTModel
from tendril.db.models.content import MediaContentInfoFullTModel

from tendril.utils import log
logger = log.get_logger(__name__)


class ImageSetDefaultDurationResponseTModel(TendrilTBaseModel):
    interest_id: int
    default_duration: int


class ImageSetColorsResponseTModel(TendrilTBaseModel):
    interest_id: int
    bgcolor: Optional[str]
    color: Optional[str]


class ImageSetAddTModel(TendrilTBaseModel):
    storedfile_id: int
    position: Optional[int]
    duration: Optional[int]


class InterestImageSetRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestImageSetRouterGenerator, self).__init__()
        self._actual = actual

    async def upload_imageset_content(self, request: Request,
                                      id: int, background_tasks: BackgroundTasks,
                                      file: UploadFile = File(...),
                                      user: AuthUserModel = auth_spec()):
        # TODO We always allow this, since we don't enforce approvals on imagesets. This needs
        #    additional thought and possibly a way to inject approval requirements on a case
        #    by case basis.
        with get_session() as session:
            interest: InterestImageSetMixin = self._actual.item(id=id, session=session)

            # Ensure we accept the file extension
            file_name, file_ext = os.path.splitext(file.filename)
            if file_ext not in IMAGESET_EXTENSIONS:
                raise FileTypeUnsupported(file_ext, IMAGESET_EXTENSIONS,
                                          'add_artefact', interest.id, interest.name,)

            # Get Auth clearance before sending the task to the background. This will
            # raise an exception if there is a problem.
            interest.upload_imageset_content(probe_only=True, auth_user=user, session=session)

            # Confirm we have a valid UUIDv1 filename. If we don't, that probably means the
            # frontend didn't do it's job, so we provide a random UUID instead.
            try:
                assert file_name[:3] == 'is_'
                _ = uuid.UUID(file_name[3:], version=1)
                storage_filename = f'{file_name}{file_ext}'
            except (ValueError, AssertionError):
                # logger.warn(f"Got a non-compliant filename {file_name} from the frontend for an imageset "
                #             "upload. Check frontend implementation. We want a UUIDv1 prefixed by 'is_'.")
                storage_filename = f"is_{uuid.uuid4()}{file_ext}"

            # The above prechecks are required at the API level here since we are delegating
            # to a background task, and we want to avoid forcing the client to deal with
            # exceptions in that context.

            # TODO Consider providing a helper function in the interest iteself to do
            #  this stuff instead. The interest otherwise remains bare and unprotected.

            # Generate Upload Ticket and return
            upload_token = tokens.open(
                namespace='isu',
                metadata={'interest_id': interest.id,
                          'filename': storage_filename},
                user=user.id, current="Request Created",
                progress_max=1, ttl=600,
            )

            background_tasks.add_task(interest.upload_imageset_content,
                                      file=file,
                                      rename_to=storage_filename,
                                      token_id=upload_token.id,
                                      auth_user=user, session=session)

        return upload_token
    #
    # async def format_info(self, request: Request, id: int, format_id: int,
    #                       full: bool = True,
    #                       user: AuthUserModel = auth_spec()):
    #     with get_session() as session:
    #         interest: MediaContentInterest = self._actual.item(id=id, session=session)
    #         return interest.format_information(format_id, full=full, auth_user=user, session=session)
    #
    # async def delete_media_format(self, request: Request,
    #                               id: int, filename: str,
    #                               user: AuthUserModel = auth_spec()):
    #     """
    #     Warning : This can only be done when the interest is in the NEW state. This
    #               enforces approval requirements on any change in the formats. An additional
    #               API endpoint (something like reset approvals?) is needed for this.
    #     """
    #     pass
    #
    # async def generate_provider_content(self, request:Request, id:int,
    #                                     provider_id:int, args: dict=Body(...),
    #                                     user: AuthUserModel = auth_spec()):
    #     with get_session() as session:
    #         interest: MediaContentInterest = self._actual.item(id=id, session=session)
    #         return interest.generate_from_provider(provider_id, args=args, auth_user=user, session=session)

    """
    This won't have any effect for most interests. Only in those cases where the imageset is  
    core to the interest's reason for existing, where display of the imageset has a specialized 
    interface will this matter.
    """
    async def set_imageset_default_duration(self, request:Request, id: int,
                                            duration: int = 10,
                                            user: AuthUserModel = auth_spec()):
        with get_session() as session:
            interest: InterestImageSetMixin = self._actual.item(id=id, session=session)
            return interest.imageset_set_default_duration(default_duration=duration, auth_user=user, session=session)

    """
    This won't have any effect for most interests. 
    
    Only in those cases where the imageset is core to the interest's reason for existing, 
    where display of the imageset has a specialized interface will this matter. In those 
    cases, bgcolor may be used to determine the background color of the image.
    
    Color is not presently used anywhere. In the future, it is intended to use the bgcolor
    color combination alongside the imageset itself to provide some scaffolding for branding
    on a per-interest basis.
    """
    async def set_imageset_colors(self, request: Request, id: int,
                                  bgcolor: str = None,
                                  color: str = None,
                                  user: AuthUserModel = auth_spec()):
        with get_session() as session:
            interest: InterestImageSetMixin = self._actual.item(id=id, session=session)
            return interest.imageset_set_colors(bgcolor=bgcolor, color=color, auth_user=user, session=session)

    async def get_imageset_contents(self, request: Request, id: int,
                                    user: AuthUserModel = auth_spec()):
        with get_session() as session:
            interest: InterestImageSetMixin = self._actual.item(id=id, session=session)
            return interest.imageset_get_contents(auth_user=user, session=session)

    async def add_to_imageset(self, request:Request, id:int, item: ImageSetAddTModel,
                              user: AuthUserModel = auth_spec()):
        with get_session() as session:
            interest: InterestImageSetMixin = self._actual.item(id=id, session=session)
            result = interest.imageset_add(**item.dict(), auth_user=user, session=session)

        if not result:
            raise Exception

        with get_session() as session:
            interest: InterestImageSetMixin = self._actual.item(id=id, session=session)
            return interest.imageset_get_contents(auth_user=user, session=session)

    async def remove_from_imageset(self, request:Request, id: int, position: int,
                                   user: AuthUserModel = auth_spec()):
        with get_session() as session:
            interest: InterestImageSetMixin = self._actual.item(id=id, session=session)
            result = interest.imageset_remove(position=position, auth_user=user, session=session)

        if not result:
            raise Exception

        with get_session() as session:
            interest: InterestImageSetMixin = self._actual.item(id=id, session=session)
            return interest.imageset_get_contents(auth_user=user, session=session)

    async def change_item_duration(self, request:Request, id:int,
                                   position:int, duration:int,
                                   user: AuthUserModel = auth_spec()):
        pass

    def generate(self, name):
        desc = f'ImageSet API for {titleize(singularize(name))} Interests'
        prefix = self._actual.interest_class.model.role_spec.prefix
        router = APIRouter(prefix=f'/{name}', tags=[desc],
                           dependencies=[Depends(authn_dependency)])

        router.add_api_route("/{id}/imageset/upload", self.upload_imageset_content, methods=["POST"],
                             response_model=GenericTokenTModel,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        # router.add_api_route("/{id}/imageset/delete", self.delete_imageset_content, methods=["POST"],
        #                      # response_model=[],
        #                      dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        router.add_api_route("/{id}/imageset/duration", self.set_imageset_default_duration, methods=['POST'],
                             response_model=ImageSetDefaultDurationResponseTModel,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        router.add_api_route("/{id}/imageset/colors", self.set_imageset_colors, methods=['POST'],
                             response_model=ImageSetColorsResponseTModel,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        router.add_api_route("/{id}/imageset", self.get_imageset_contents, methods=['GET'],
                             # response_model=,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        router.add_api_route("/{id}/imageset/add", self.add_to_imageset, methods=['POST'],
                            # response_model=,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        router.add_api_route("/{id}/imageset/remove/{position}", self.remove_from_imageset, methods=['POST'],
                             # response_model=,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        return [router]
