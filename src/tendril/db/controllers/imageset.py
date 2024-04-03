

from sqlalchemy.exc import NoResultFound

from tendril.db.models.imageset import ImageSetModel
from tendril.db.models.imageset import ImageSetAssociationModel

from tendril.utils.db import with_db


@with_db
def get_imageset(id, raise_if_none=True, session=None):
    filters = [ImageSetModel.id == id]
    q = session.query(ImageSetModel).filter(*filters)
    try:
        return q.one()
    except NoResultFound:
        if raise_if_none:
            raise
        return None


@with_db
def create_imageset(id=None, session=None, **kwargs):
    if id:
        try:
            existing = get_imageset(id=id, session=session)
        except NoResultFound:
            pass
        else:
            raise ValueError(f"Could not create content container with "
                             f"ID {id}. Already Exists.")
    imageset = ImageSetModel(id=id)
    session.add(imageset)
    session.flush()
    return imageset

# TODO The functions below are pulled from device_content sequences. They
#  have some changes, but not a lot. Consider if they can be repackaged
#  into some kind of reusable mixin or so.

@with_db
def imageset_next_position(id=None, session=None):
    try:
        imageset = get_imageset(id=id, session=session)
        return max([x.position for x in imageset.contents], default=-1) + 1
    except NoResultFound:
        raise ValueError(f"Could not find an 'imageset' "
                         f"container with the provided id {id}")


@with_db
def imageset_get_at_position(id, position, session=None):
    try:
        imageset = get_imageset(id=id, session=session)
        for x in imageset.contents:
            if x.position == position:
                return x
    except NoResultFound:
        raise ValueError(f"Could not find an 'imageset' "
                         f"container with the provided id {id}")


@with_db
def imageset_prep_position(id, position, session=None):
    existing = imageset_get_at_position(id, position, session=session)
    if not existing:
        return
    imageset_prep_position(id, position + 1, session=session)
    existing.position = position + 1
    session.flush()


@with_db
def imageset_get_contents(id, session=None):
    try:
        imageset = get_imageset(id=id, session=session)
    except NoResultFound:
        raise ValueError(f"Could not find a 'imageset' "
                         f"container with the provided id {id}")
    return [{
        'position': c.position,
        'duration': c.duration,
        'content': c.storedfile,
    } for c in imageset.contents]


@with_db
def imageset_add_content(id, storedfile, position=None, duration=None, session=None):
    storedfile_id = storedfile
    if position is None:
        position = imageset_next_position(id=id, session=session)
    else:
        imageset_prep_position(id, position, session=session)
    if not storedfile_id:
        raise ValueError(f"Don't have a valid storedfile_id. Got {storedfile}")
    association = ImageSetAssociationModel(imageset_id=id,
                                           storedfile_id=storedfile_id,
                                           position=position,
                                           duration=duration)
    session.add(association)
    session.commit()


@with_db
def imageset_remove_content(id, position, session=None):
    assn = imageset_get_at_position(id=id, position=position, session=session)
    if not assn:
        raise ValueError(f"Imageset does not seem to have any "
                         f"content at position {position}.")
    session.delete(assn)
    session.commit()


@with_db
def imageset_pull_back_position(id, position, to_position, session=None):
    assn = imageset_get_at_position(id=id, position=position, session=session)
    if not assn:
        imageset_pull_back_position(id, position + 1, to_position, session=session)
    else:
        assn.position = to_position
        session.commit()


@with_db
def imageset_heal_positions(id=None, session=None):
    try:
        imageset = get_imageset(id=id, session=session)
        session.expire(imageset)
        if not len(imageset.contents):
            return
        for position in range(len(imageset.contents)):
            if not imageset_get_at_position(id=id, position=position, session=session):
                imageset_pull_back_position(id=id, position=position + 1, to_position=position, session=session)
    except NoResultFound:
        raise ValueError(f"Could not find a 'imageset' "
                         f"container with the provided id {id}")
