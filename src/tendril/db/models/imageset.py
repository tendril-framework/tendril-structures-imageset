

from typing import List
from typing import Optional
from sqlalchemy import Column
from sqlalchemy import VARCHAR
from sqlalchemy import Integer
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from tendril.utils.db import DeclBase
from tendril.utils.db import BaseMixin
from tendril.utils.db import TimestampMixin
from tendril.filestore.db.model import StoredFileModel
from tendril.utils.pydantic import TendrilTBaseModel


class ImageSetModel(DeclBase, BaseMixin, TimestampMixin):

    id = Column(Integer, primary_key=True)
    default_duration = Column(Integer, nullable=False, default=10)
    bgcolor = Column(VARCHAR(9), nullable=True)
    color = Column(VARCHAR(9), nullable=True)

    contents: Mapped[List["ImageSetAssociationModel"]] = \
        relationship(order_by="ImageSetAssociationModel.position")

    def export(self, full=False):
        rv = {
            'default_duration': self.default_duration,
            'bgcolor': self.bgcolor,
            'color': self.color,
            'contents': [x.export() for x in self.contents]
        }
        return rv


class ImageSetAssociationModel(DeclBase):
    __tablename__ = "ImageSetAssociation"
    imageset_id: Mapped[int] = mapped_column(ForeignKey("ImageSet.id"), primary_key=True)
    storedfile_id: Mapped[int] = mapped_column(ForeignKey("StoredFile.id"))
    position: Mapped[int] = mapped_column(primary_key=True)
    duration: Mapped[Optional[int]]
    imageset: Mapped[ImageSetModel] = relationship(back_populates="contents", foreign_keys=[imageset_id], lazy='selectin')
    storedfile: Mapped[StoredFileModel] = relationship(foreign_keys=[storedfile_id], lazy='joined')

    def export(self):
        return {
            'position': self.position,
            'duration': self.duration,
            'storedfile_id': self.storedfile_id,
            'content': self.storedfile.expose_uri,
        }
